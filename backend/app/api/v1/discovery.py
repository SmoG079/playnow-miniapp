"""Public location resolution; map credentials stay on the server."""
import httpx
from app.services.tencent_map import GEOCODER_URL, geocoder_params
from fastapi import APIRouter, HTTPException, Query, Request
from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.rate_limit import check_rate_limit
router=APIRouter(prefix='/discovery',tags=['discovery'])
logger=get_logger(__name__)

def parse_city(data):
    if data.get('status')!=0: raise HTTPException(502,'城市定位失败，请手动选择城市')
    result=data.get('result') or {}
    region=result.get('address_component') or result.get('ad_info') or {}
    province=region.get('province','')
    city=region.get('city','')
    district=region.get('district','')
    if city in ('市辖区','县') and province.endswith('市'): city=province
    if city in ('省直辖县级行政区划','自治区直辖县级行政区划'): city=district
    if not city: raise HTTPException(502,'未能识别城市，请手动选择')
    ad_info = result.get("ad_info") or {}
    adcode = str(ad_info.get("adcode") or region.get("adcode") or "")
    return dict(city=city,province=province,district=district,adcode=adcode if len(adcode) == 6 and adcode.isdigit() else None)

@router.get('/location-city')
async def location_city(request:Request,lat:float=Query(...,ge=-90,le=90),lng:float=Query(...,ge=-180,le=180)):
    settings=get_settings()
    key=settings.TENCENT_MAP_KEY
    if not key: raise HTTPException(503,'城市定位暂不可用，请手动选择城市')
    await check_rate_limit('discovery:city:'+ (request.client.host if request.client else 'unknown'),30,60)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response=await client.get(GEOCODER_URL, params=geocoder_params({'location':f'{lat},{lng}','get_poi':0},key,getattr(settings,'TENCENT_MAP_SK','')), headers={'x-legacy-url-decode':'no'})
            response.raise_for_status()
            data=response.json()
    except (httpx.HTTPError,ValueError):
        # Never log the request URL: it includes the credential.
        logger.error('City lookup provider failed')
        raise HTTPException(502,'城市定位失败，请手动选择城市')
    return dict(**parse_city(data),latitude=lat,longitude=lng)


@router.get('/weather')
async def weather(request: Request, city: str = Query(..., min_length=1, max_length=64),
                  province: str = Query('', max_length=64),
                  adcode: str | None = None, lat: float | None = None, lng: float | None = None):
    from app.services.weather import city_weather
    city, province = city.strip(), province.strip()
    if not city:
        raise HTTPException(422, '请选择城市')
    settings = get_settings()
    if not settings.TENCENT_MAP_KEY:
        raise HTTPException(503, '天气暂不可用')
    await check_rate_limit('discovery:weather:' + (request.client.host if request.client else 'unknown'), 30, 60)
    return await city_weather(city, province, settings.TENCENT_MAP_KEY, getattr(settings, 'TENCENT_MAP_SK', ''),
        adcode=adcode, latitude=lat, longitude=lng)


from datetime import date as Date
from typing import Literal
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db

@router.get('/activities')
async def activities(city: str | None = None,
    activity_type: Literal['all','post','free','venue','tournament'] = 'all',
    ntrp_levels: str | None = Query(None,max_length=128), on_date: Date | None = None,
    sort_by: Literal['created','date_asc','date_desc','distance'] = 'date_asc',
    lat: float | None = Query(None,ge=-90,le=90), lng: float | None = Query(None,ge=-180,le=180),
    page: int = Query(1,ge=1), page_size: int = Query(20,ge=1,le=50), status: str | None = Query(None,max_length=20), db: AsyncSession = Depends(get_db)):
    from app.services.activity_discovery import list_activities
    return await list_activities(db,city,activity_type,ntrp_levels,on_date,sort_by,lat,lng,page,page_size,status)
