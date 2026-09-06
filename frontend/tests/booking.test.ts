import { describe, it, expect } from 'vitest'
import { selectSlot, canBook, totalPrice, filterActivities, type Slot } from '../src/domain/booking'
const slot = (index: number, court = 0, available = true): Slot => ({ id: `${court}-${index}`, court, index, price: index > 3 ? 50 : 40, available })
describe('prototype booking rules', () => {
  it('requires at least one hour and prices each half hour', () => {
    const first = selectSlot([], slot(3)).slots
    expect(canBook(first)).toBe(false)
    const second = selectSlot(first, slot(4)).slots
    expect(canBook(second)).toBe(true)
    expect(totalPrice(second)).toBe(90)
  })
  it('rejects booked cells, gaps and cross-court selection', () => {
    const first = [slot(0)]
    for (const cell of [slot(1,0,false),slot(3),slot(1,1)]) {
      expect(selectSlot(first,cell).error).toBeTruthy()
      expect(selectSlot(first,cell).slots).toEqual(first)
    }
  })
  it('truncates later slots when deselecting to preserve continuity', () => {
    expect(selectSlot([slot(0),slot(1),slot(2)],slot(1)).slots).toEqual([slot(0)])
  })
  it('combines date, level and feed filters', () => {
    const items = [{day:0,level:3,kind:'match'},{day:1,level:3,kind:'tournament'}]
    expect(filterActivities(items,0,'3.0','match')).toEqual([items[0]])
    expect(filterActivities(items,1,'4.0','match')).toEqual([])
  })
})
