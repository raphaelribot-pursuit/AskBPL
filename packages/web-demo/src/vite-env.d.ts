/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_DOCUMENTS_PUBLIC_BASE?: string
  /** When "true", skip heavy Spline bundle; book emoji avatar only (pilot demos on slow networks). */
  readonly VITE_LITE_DEMO?: string
  /**
   * When "true", mount `@splinetool/react-spline` if `HEAD` on the scene URL succeeds.
   * Default (unset) keeps the SVG book — avoids WebGL/renderer black-screen crashes on some GPUs.
   */
  readonly VITE_ENABLE_SPLINE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
