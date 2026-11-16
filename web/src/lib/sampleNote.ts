/** The evidence-floor note as plain text: a value backed by fewer than `min` samples. */
export function sampleNoteText(sample: number, min: number, noun: string): string {
  return `Too few ${noun} (${sample} of ${min})`;
}
