/** Cloudflare Worker entry point for the vinext-starter template. */
import { handleImageOptimization, DEFAULT_DEVICE_SIZES, DEFAULT_IMAGE_SIZES } from "vinext/server/image-optimization";
import handler from "vinext/server/app-router-entry";

declare const __CIVICDECISION_BUILD_COMMIT__: string;
declare const __CIVICDECISION_BUILD_TREE__: string;
declare const __CIVICDECISION_BUILD_TAG__: string;
declare const __CIVICDECISION_BUILD_DIRTY__: string;
declare const __CIVICDECISION_BUILD_TIME__: string;
declare const __CIVICDECISION_PACKAGE_VERSION__: string;
declare const __CIVICDECISION_HOSTING_PROJECT_ID__: string;

interface Env {
  ASSETS: Fetcher;
  IMAGES: {
    input(stream: ReadableStream): {
      transform(options: Record<string, unknown>): {
        output(options: { format: string; quality: number }): Promise<{ response(): Response }>;
      };
    };
  };
}

interface ExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
  passThroughOnException(): void;
}

// Image security config. SVG sources with .svg extension auto-skip the
// optimization endpoint on the client side (served directly, no proxy).
// To route SVGs through the optimizer (with security headers), set
// dangerouslyAllowSVG: true in next.config.js and uncomment below:
// const imageConfig: ImageConfig = { dangerouslyAllowSVG: true };

const worker = {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/build-info.json") {
      const dirty = __CIVICDECISION_BUILD_DIRTY__ === "true";
      const exactSource =
        __CIVICDECISION_BUILD_COMMIT__ !== "unavailable" &&
        __CIVICDECISION_BUILD_TREE__ !== "unavailable" &&
        __CIVICDECISION_BUILD_TAG__ !== "untagged" &&
        !dirty;
      return Response.json(
        {
          schemaVersion: "1.0.0",
          project: "CivicDecision OS",
          repository: "limingrui679-design/civicdecision-os",
          packageVersion: __CIVICDECISION_PACKAGE_VERSION__,
          commit: __CIVICDECISION_BUILD_COMMIT__,
          tree: __CIVICDECISION_BUILD_TREE__,
          releaseTag: __CIVICDECISION_BUILD_TAG__,
          dirty,
          sourceIdentity: exactSource ? "exact-tagged-clean-source" : "local-or-unverified-source",
          builtAt: __CIVICDECISION_BUILD_TIME__,
          hostingProjectId: __CIVICDECISION_HOSTING_PROJECT_ID__,
          evidenceBoundary:
            "A public read-only walkthrough is not evidence of production deployment, external review, users, adoption, or real-world impact.",
        },
        {
          headers: {
            "Cache-Control": "no-store",
            "Content-Type": "application/json; charset=utf-8",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
          },
        },
      );
    }

    if (url.pathname === "/_vinext/image") {
      const allowedWidths = [...DEFAULT_DEVICE_SIZES, ...DEFAULT_IMAGE_SIZES];
      return handleImageOptimization(request, {
        fetchAsset: (path) => env.ASSETS.fetch(new Request(new URL(path, request.url))),
        transformImage: async (body, { width, format, quality }) => {
          const result = await env.IMAGES.input(body).transform(width > 0 ? { width } : {}).output({ format, quality });
          return result.response();
        },
      }, allowedWidths);
    }

    return handler.fetch(request, env, ctx);
  },
};

export default worker;
