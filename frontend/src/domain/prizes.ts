export interface Prize { name: string; description: string }
export function normalizedPrizes(prizes: Prize[]): Prize[] {
  return prizes.map(p => ({name:p.name.trim(),description:p.description.trim()})).filter(p=>p.name||p.description);
}
export function displayedPrizes(prizes: Prize[] | null | undefined, legacy?: string): Prize[] {
  return prizes == null ? (legacy?.trim() ? [{name:'奖项',description:legacy}] : []) : prizes;
}
