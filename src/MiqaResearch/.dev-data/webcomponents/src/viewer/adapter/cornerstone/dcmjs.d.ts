// The parts of dcmjs (0.52, no bundled types) the adapter uses directly; `@cornerstonejs/adapters` uses the rest.
declare module "dcmjs" {
  type Dataset = Record<string, unknown>;
  const dcmjs: {
    data: {
      /** A naturalized dataset (with `_meta`) as a DICOM Part 10 file; `write()` gives its bytes. */
      datasetToDict(dataset: Dataset): { write(): ArrayBuffer };
      DicomMetaDictionary: {
        /** DICOM JSON (PS3.18 F.2) → naturalized dataset (keywords, sequences as arrays with accessors). */
        naturalizeDataset(json: unknown): Dataset;
      };
      Colors: {
        /** sRGB in 0–1 → DICOM CIELab (0–65535). */
        rgb2DICOMLAB(rgb: number[]): number[];
        /** DICOM CIELab (0–65535) → sRGB in 0–1. */
        dicomlab2RGB(lab: number[]): number[];
      };
    };
    normalizers: {
      /** Naturalized SOP instances → one multiframe dataset (what the SEG reader expects). */
      Normalizer: { normalizeToDataset(datasets: Dataset[]): Dataset };
    };
  };
  export default dcmjs;
}
