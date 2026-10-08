"""Shared discovery predicates and ordering, applied before pagination."""
from sqlalchemy import func, case

def city_name(city):
    return (city or '').strip() or None

def distance_expr(lat, lng, latitude, longitude):
    cosine = (func.sin(func.radians(latitude))*func.sin(func.radians(lat))
              +func.cos(func.radians(latitude))*func.cos(func.radians(lat))
              *func.cos(func.radians(longitude-lng)))
    bounded=case((cosine>1,1),(cosine< -1,-1),else_=cosine)
    return 6371*func.acos(bounded)

def ordered(query, sort, date_column, id_column, lat=None, lng=None, latitude=None, longitude=None):
    if sort=='distance':
        if lat is None or lng is None:
            from fastapi import HTTPException
            raise HTTPException(422,'距离排序需要定位，请开启定位或选择日期排序')
        distance=distance_expr(lat,lng,latitude,longitude)
        return query.order_by(distance.is_(None),distance.asc(),date_column.asc(),id_column.desc())
    if sort=='date_desc': return query.order_by(date_column.desc(),id_column.desc())
    if sort=='date_asc': return query.order_by(date_column.asc(),id_column.desc())
    return query.order_by(id_column.desc())
