/**
 * The evidence-floor note: a value backed by fewer than `min` samples.
 * Bare text — the caller decides when it shows and wraps it.
 */
export function SampleNote({ sample, min, noun }: { sample: number; min: number; noun: string }) {
  return <>{`Too few ${noun} (${sample} of ${min})`}</>;
}
