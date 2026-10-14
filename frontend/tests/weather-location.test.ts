import { describe, expect, it } from "vitest";
import { regionWeatherAdcode, weatherPosition } from "../src/domain/weather";
describe("weather administrative metadata",()=>{
  it("selects the city, municipality or province-administered county code",()=>{
    expect(regionWeatherAdcode(["江苏省","扬州市","广陵区"],["320000","321000","321002"])).toBe("321000");
    expect(regionWeatherAdcode(["北京市","市辖区","朝阳区"],["110000","110100","110105"])).toBe("110000");
    expect(regionWeatherAdcode(["河南省","省直辖县级行政区划","济源市"],["410000","419000","419001"])).toBe("419001");
  });
  it("uses session coordinates when available and administrative codes after reopening",()=>{
    expect(weatherPosition({city:"扬州市",province:"江苏省",latitude:0,longitude:0,adcode:"321000"})).toBe("lat=0&lng=0");
    expect(weatherPosition({city:"扬州市",province:"江苏省",adcode:"321000"})).toBe("adcode=321000");
  });
  it("rejects missing/malformed location metadata",()=>{
    expect(regionWeatherAdcode(["江苏省","扬州市"])).toBeUndefined();
    expect(weatherPosition({city:"扬州市",province:"江苏省",latitude:NaN,longitude:119})).toBe("");
    expect(weatherPosition({city:"扬州市",province:"江苏省",adcode:"wrong"})).toBe("");
  });
});
