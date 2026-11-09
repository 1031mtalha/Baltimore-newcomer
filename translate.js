/* Google Website Translator, restored from the pre-July-25 version of the site.
   Google has announced end of support for this widget on Oct 1, 2026. */
(function () {
  var host = location.hostname;

  function clearCookie() {
    var gone = 'googtrans=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    document.cookie = gone;
    document.cookie = gone + ' domain=' + host;
    document.cookie = gone + ' domain=.' + host;
  }

  document.addEventListener('click', function (e) {
    var link = e.target.closest('[data-gtlang]');
    if (!link) return;
    e.preventDefault();
    var lang = link.getAttribute('data-gtlang');

    if (lang === 'en') {
      clearCookie();
      location.reload();
      return;
    }
    var select = document.querySelector('.goog-te-combo');
    if (select) {
      select.value = lang;
      select.dispatchEvent(new Event('change'));
      return;
    }
    document.cookie = 'googtrans=/en/' + lang + '; path=/';
    document.cookie = 'googtrans=/en/' + lang + '; path=/; domain=.' + host;
    location.reload();
  });

  window.googleTranslateElementInit = function () {
    new google.translate.TranslateElement({
      pageLanguage: 'en',
      includedLanguages: 'ar,fa,fr,ps,es,uk,so,ti',
      layout: google.translate.TranslateElement.InlineLayout.SIMPLE,
      autoDisplay: false
    }, 'google_translate_element');
  };

  var s = document.createElement('script');
  s.src = 'https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit';
  s.async = true;
  document.head.appendChild(s);
})();
