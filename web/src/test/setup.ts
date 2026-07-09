import "@testing-library/jest-dom";

// jsdom does not implement matchMedia; antd's responsive Grid/Table
// components call it on mount. Polyfill so components render in tests.
if (!window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}
