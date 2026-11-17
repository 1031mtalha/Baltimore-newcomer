/* "City or County?" lookup.
   An address is checked with the U.S. Census Bureau geocoder, which returns the
   county directly (Baltimore city = 24510, Baltimore County = 24005). If Census
   cannot match the address, OpenStreetMap finds it and the point is tested
   against Census boundary lines, which is approximate near the border.
   A 5-digit ZIP code is checked against the Census 2020 ZIP-to-county table. */
(function () {
  var section = document.getElementById('lookup');
  if (!section) return;

  var CITY = '24510', COUNTY = '24005';
  var form = document.getElementById('lookup-form');
  var input = document.getElementById('lookup-input');
  var button = form.querySelector('button');
  var result = document.getElementById('lookup-result');
  var mapEl = document.getElementById('lookup-map');

  var zips = null, bounds = null, map = null, marker = null, outline = null;

  var COUNTY_OFFICE = 'https://www.baltimorecountymd.gov/departments/county-executive/immigrant-affairs';
  var CITY_OFFICE = 'https://www.baltimorecity.gov/mima';

  function loadData() {
    return Promise.all([
      fetch('data/zip_county.json').then(function (r) { return r.json(); }),
      fetch('data/baltimore_boundaries.geojson').then(function (r) { return r.json(); })
    ]).then(function (d) { zips = d[0]; bounds = d[1]; });
  }

  function cssVar(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  function initMap() {
    if (map || typeof L === 'undefined') return;
    map = L.map(mapEl, { scrollWheelZoom: false }).setView([39.39, -76.6], 9);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors; boundaries: U.S. Census Bureau'
    }).addTo(map);
    var layer = L.geoJSON(bounds, {
      style: function (f) {
        var city = f.properties.GEOID === CITY;
        return { color: city ? '#b3502f' : '#1f6b64', weight: 2, fillOpacity: city ? 0.18 : 0.08 };
      },
      onEachFeature: function (f, l) {
        l.bindTooltip(f.properties.GEOID === CITY ? 'Baltimore City' : 'Baltimore County', { sticky: true });
      }
    }).addTo(map);
    outline = layer.getBounds();
    map.fitBounds(outline);
  }

  function showPoint(lat, lon) {
    if (!map) return;
    if (marker) marker.remove();
    marker = L.circleMarker([lat, lon], { radius: 9, color: '#ffffff', weight: 3, fillColor: '#0c2634', fillOpacity: 1 }).addTo(map);
    map.setView([lat, lon], 12);
  }

  function say(html, kind) {
    result.className = 'lookup-result' + (kind ? ' is-' + kind : '');
    result.innerHTML = html;
  }

  function verdict(geoid, matched, approximate, subject) {
    subject = subject || 'This address';
    var where = matched ? '<span class="lookup-matched">' + escapeHtml(matched) + '</span><br>' : '';
    var note = approximate
      ? '<p class="lookup-note">This answer is approximate. If you live close to the City/County line, confirm with 211.</p>'
      : '';
    if (geoid === CITY) {
      return say(where + '<strong>' + subject + ' is in Baltimore City.</strong>' +
        '<p>Use Baltimore City and statewide services. Baltimore County programs may not serve you.' +
        ' City contact for immigrant families: <a href="' + CITY_OFFICE + '">Mayor’s Office of Immigrant Affairs</a>.</p>' + note, 'city');
    }
    if (geoid === COUNTY) {
      return say(where + '<strong>' + subject + ' is in Baltimore County.</strong>' +
        '<p>Use Baltimore County and statewide services. Many resources on this page are Baltimore City programs and may not serve you.' +
        ' County contact for immigrant families: <a href="' + COUNTY_OFFICE + '">Baltimore County Office of Immigrant Affairs</a>.</p>' + note, 'county');
    }
    return say(where + '<strong>' + subject + ' is outside Baltimore City and Baltimore County.</strong>' +
      '<p>Call or text 211 to find services where you live.</p>' + note, 'outside');
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function resetMap() {
    if (marker) { marker.remove(); marker = null; }
    if (map && outline) map.fitBounds(outline);
  }

  function checkZip(zip) {
    resetMap();
    var d = zips[zip];
    var city = d && d[CITY] || 0, county = d && d[COUNTY] || 0;
    if (!d) return say('<strong>ZIP ' + zip + ' is outside Baltimore City and Baltimore County.</strong><p>Call or text 211 to find services where you live.</p>', 'outside');
    if (city >= 0.99) return verdict(CITY, null, false, 'ZIP ' + zip);
    if (county >= 0.99) return verdict(COUNTY, null, false, 'ZIP ' + zip);
    var parts = [];
    if (city) parts.push('Baltimore City');
    if (county) parts.push('Baltimore County');
    if (city + county < 0.99) parts.push('a neighboring county');
    say('<strong>ZIP ' + zip + ' is split between ' + parts.join(' and ') + '.</strong>' +
      '<p>Enter your full street address to get an exact answer.</p>', 'split');
  }

  function census(address) {
    return new Promise(function (resolve, reject) {
      var cb = 'censusCb' + Date.now();
      var s = document.createElement('script');
      var timer = setTimeout(function () { cleanup(); reject(new Error('timeout')); }, 12000);
      function cleanup() { clearTimeout(timer); delete window[cb]; s.remove(); }
      window[cb] = function (data) { cleanup(); resolve(data); };
      s.onerror = function () { cleanup(); reject(new Error('network')); };
      s.src = 'https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress' +
        '?address=' + encodeURIComponent(address) +
        '&benchmark=Public_AR_Current&vintage=Current_Current&layers=Counties' +
        '&format=jsonp&callback=' + cb;
      document.head.appendChild(s);
    });
  }

  function osm(address) {
    var url = 'https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&countrycodes=us' +
      '&viewbox=-77.0,39.8,-76.2,39.1&bounded=1&q=' + encodeURIComponent(address);
    return fetch(url, { headers: { 'Accept': 'application/json' } }).then(function (r) { return r.json(); });
  }

  function inRing(x, y, ring) {
    var inside = false;
    for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      var xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }

  function countyAt(lon, lat) {
    for (var k = 0; k < bounds.features.length; k++) {
      var f = bounds.features[k], g = f.geometry;
      var polys = g.type === 'Polygon' ? [g.coordinates] : g.coordinates;
      for (var p = 0; p < polys.length; p++) {
        if (inRing(lon, lat, polys[p][0])) {
          var hole = false;
          for (var h = 1; h < polys[p].length; h++) if (inRing(lon, lat, polys[p][h])) hole = true;
          if (!hole) return f.properties.GEOID;
        }
      }
    }
    return null;
  }

  function checkAddress(raw) {
    var address = /\b(MD|Maryland)\b/i.test(raw) ? raw : raw + ', MD';
    say('Looking up the address…');
    return census(address).then(function (data) {
      var m = data && data.result && data.result.addressMatches && data.result.addressMatches[0];
      if (m) {
        var c = (m.geographies.Counties || [])[0];
        showPoint(m.coordinates.y, m.coordinates.x);
        return verdict(c ? c.GEOID : null, m.matchedAddress, false);
      }
      throw new Error('nomatch');
    }).catch(function () {
      return osm(address).then(function (list) {
        if (!list || !list.length) {
          return say('<strong>We couldn’t find that address.</strong><p>Check the spelling and include the street number, street name and ZIP code, for example “100 Holliday St, Baltimore, MD 21202”.</p>', 'outside');
        }
        var lat = parseFloat(list[0].lat), lon = parseFloat(list[0].lon);
        showPoint(lat, lon);
        verdict(countyAt(lon, lat), list[0].display_name, true);
      });
    }).catch(function () {
      say('<strong>The lookup isn’t working right now.</strong><p>Try again later, or call 211 and ask whether your address is in Baltimore City or Baltimore County.</p>', 'outside');
    });
  }

  var ready = loadData().then(initMap).catch(function () {
    say('The lookup could not load. Call 211 for help.', 'outside');
  });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var v = input.value.trim();
    if (!v) { input.focus(); return; }
    button.disabled = true;
    ready.then(function () {
      if (/^\d{5}$/.test(v)) return checkZip(v);
      return checkAddress(v);
    }).then(function () { button.disabled = false; }, function () { button.disabled = false; });
  });
})();
