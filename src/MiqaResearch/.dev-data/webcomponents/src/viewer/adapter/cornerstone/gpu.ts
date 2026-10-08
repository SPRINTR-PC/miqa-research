// GPU texture limits for the size guard (#283), read once from a throwaway WebGL2 context.
// Neither CS3D nor vtk.js checks MAX_3D_TEXTURE_SIZE, so an oversized volume would fail silently.
import { WEBGL2_MINIMUM, type GpuLimits } from "../../size-guard.ts";

let limits: GpuLimits | undefined;

export function gpuLimits(): GpuLimits {
  if (limits) return limits;
  const gl = document.createElement("canvas").getContext("webgl2");
  if (!gl) return WEBGL2_MINIMUM;
  limits = {
    max3dTextureSize: Number(gl.getParameter(gl.MAX_3D_TEXTURE_SIZE)) || WEBGL2_MINIMUM.max3dTextureSize,
    maxTextureSize: Number(gl.getParameter(gl.MAX_TEXTURE_SIZE)) || WEBGL2_MINIMUM.maxTextureSize,
  };
  gl.getExtension("WEBGL_lose_context")?.loseContext();
  return limits;
}
