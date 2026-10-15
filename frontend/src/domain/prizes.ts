export interface Prize { name: string; description: string }
export function normalizedPrizes(prizes: Prize[]): Prize[] {
  return prizes.map(p => ({name:p.name.trim(),description:p.description.trim()})).filter(p=>p.name||p.description);
}
