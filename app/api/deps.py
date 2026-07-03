from fastapi import Request

from app.intel.repository import InMemoryIntelRepository


def get_repository(request: Request) -> InMemoryIntelRepository:
    return request.app.state.repository

