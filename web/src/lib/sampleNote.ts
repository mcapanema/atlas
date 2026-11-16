/** Whether a sample is worth a note: above zero (zero shows a dash) and below the floor. */
export function showsFloorNote(sample: number, min: number): boolean {
  return sample > 0 && sample < min;
}

/** The evidence-floor note as plain text: a value backed by fewer than `min` samples. */
export function sampleNoteText(sample: number, min: number, noun: string): string {
  return `Too few ${noun} (${sample} of ${min})`;
}
