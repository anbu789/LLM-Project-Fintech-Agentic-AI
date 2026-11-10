import '@testing-library/jest-dom';

// Polyfill window.HTMLElement.prototype.scrollIntoView if not present in JSDOM
if (!window.HTMLElement.prototype.scrollIntoView) {
  window.HTMLElement.prototype.scrollIntoView = function() {};
}
