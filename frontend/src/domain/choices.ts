export type ChoiceValue = string | number;
export interface ChoiceOption {
  value: ChoiceValue;
  label: string;
  description?: string;
  disabled?: boolean;
}
