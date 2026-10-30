"""Routes for Worldview, Characters (+ timeline), Locations, and Main Plot (M2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_entity_repo, get_setting_generator
from app.db.repositories.entity_repo import EntityRepository
from app.schemas.entities import (
    AiGenerateSettingRequest,
    AiRewriteItemRequest,
    CharacterCreate,
    CharacterResponse,
    CharacterTimelineSnapshot,
    CharacterUpdate,
    LocationCreate,
    LocationResponse,
    LocationUpdate,
    MainPlotResponse,
    MainPlotUpdate,
    WorldviewCreate,
    WorldviewResponse,
    WorldviewUpdate,
)
from app.services.setting_generator import SettingGeneratorService

router = APIRouter(prefix="/novels/{novel_uid}", tags=["entities"])


# --- Worldview ---

@router.get("/worldview", response_model=list[WorldviewResponse])
def list_worldview(repo: EntityRepository = Depends(get_entity_repo)) -> list[WorldviewResponse]:
    return repo.list_worldview()


@router.post("/worldview", response_model=WorldviewResponse, status_code=status.HTTP_201_CREATED)
def create_worldview(
    payload: WorldviewCreate,
    repo: EntityRepository = Depends(get_entity_repo),
) -> WorldviewResponse:
    return repo.create_worldview(payload)


@router.put("/worldview/{entry_id}", response_model=WorldviewResponse)
def update_worldview(
    entry_id: int,
    payload: WorldviewUpdate,
    repo: EntityRepository = Depends(get_entity_repo),
) -> WorldviewResponse:
    return repo.update_worldview(entry_id, payload)


@router.delete("/worldview/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_worldview(
    entry_id: int,
    repo: EntityRepository = Depends(get_entity_repo),
) -> None:
    repo.delete_worldview(entry_id)


@router.post("/worldview/generate", response_model=list[WorldviewResponse])
async def generate_worldview(
    payload: AiGenerateSettingRequest,
    svc: SettingGeneratorService = Depends(get_setting_generator),
) -> list[WorldviewResponse]:
    return await svc.generate_worldview(instruction=payload.instruction, count=payload.count)


@router.post("/worldview/{entry_id}/rewrite", response_model=WorldviewResponse)
async def rewrite_worldview_item(
    entry_id: int,
    payload: AiRewriteItemRequest,
    svc: SettingGeneratorService = Depends(get_setting_generator),
) -> WorldviewResponse:
    return await svc.rewrite_worldview_item(entry_id, payload.instruction)


# --- Characters ---

@router.get("/characters", response_model=list[CharacterResponse])
def list_characters(repo: EntityRepository = Depends(get_entity_repo)) -> list[CharacterResponse]:
    return repo.list_characters()


@router.post("/characters", response_model=CharacterResponse, status_code=status.HTTP_201_CREATED)
def create_character(
    payload: CharacterCreate,
    repo: EntityRepository = Depends(get_entity_repo),
) -> CharacterResponse:
    return repo.create_character(payload)


@router.put("/characters/{char_id}", response_model=CharacterResponse)
def update_character(
    char_id: int,
    payload: CharacterUpdate,
    repo: EntityRepository = Depends(get_entity_repo),
) -> CharacterResponse:
    return repo.update_character(char_id, payload)


@router.delete("/characters/{char_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(
    char_id: int,
    repo: EntityRepository = Depends(get_entity_repo),
) -> None:
    repo.delete_character(char_id)


@router.get("/characters/{char_id}/timeline", response_model=CharacterTimelineSnapshot)
def get_character_timeline(
    char_id: int,
    up_to_chapter_sort: float | None = Query(default=None),
    repo: EntityRepository = Depends(get_entity_repo),
) -> CharacterTimelineSnapshot:
    return repo.get_character_timeline_snapshot(char_id, up_to_chapter_sort)


@router.post("/characters/generate", response_model=list[CharacterResponse])
async def generate_characters(
    payload: AiGenerateSettingRequest,
    svc: SettingGeneratorService = Depends(get_setting_generator),
) -> list[CharacterResponse]:
    return await svc.generate_characters(instruction=payload.instruction, count=payload.count)


@router.post("/characters/{char_id}/rewrite", response_model=CharacterResponse)
async def rewrite_character(
    char_id: int,
    payload: AiRewriteItemRequest,
    svc: SettingGeneratorService = Depends(get_setting_generator),
) -> CharacterResponse:
    return await svc.rewrite_character(char_id, payload.instruction)


# --- Locations ---

@router.get("/locations", response_model=list[LocationResponse])
def list_locations(repo: EntityRepository = Depends(get_entity_repo)) -> list[LocationResponse]:
    return repo.list_locations()


@router.post("/locations", response_model=LocationResponse, status_code=status.HTTP_201_CREATED)
def create_location(
    payload: LocationCreate,
    repo: EntityRepository = Depends(get_entity_repo),
) -> LocationResponse:
    return repo.create_location(payload)


@router.put("/locations/{loc_id}", response_model=LocationResponse)
def update_location(
    loc_id: int,
    payload: LocationUpdate,
    repo: EntityRepository = Depends(get_entity_repo),
) -> LocationResponse:
    return repo.update_location(loc_id, payload)


@router.delete("/locations/{loc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(
    loc_id: int,
    repo: EntityRepository = Depends(get_entity_repo),
) -> None:
    repo.delete_location(loc_id)


@router.post("/locations/generate", response_model=list[LocationResponse])
async def generate_locations(
    payload: AiGenerateSettingRequest,
    svc: SettingGeneratorService = Depends(get_setting_generator),
) -> list[LocationResponse]:
    return await svc.generate_locations(instruction=payload.instruction, count=payload.count)


@router.post("/locations/{loc_id}/rewrite", response_model=LocationResponse)
async def rewrite_location(
    loc_id: int,
    payload: AiRewriteItemRequest,
    svc: SettingGeneratorService = Depends(get_setting_generator),
) -> LocationResponse:
    return await svc.rewrite_location(loc_id, payload.instruction)


# --- Main Plot ---

@router.get("/main-plot", response_model=MainPlotResponse)
def get_main_plot(repo: EntityRepository = Depends(get_entity_repo)) -> MainPlotResponse:
    return repo.get_main_plot()


@router.put("/main-plot", response_model=MainPlotResponse)
def update_main_plot(
    payload: MainPlotUpdate,
    repo: EntityRepository = Depends(get_entity_repo),
) -> MainPlotResponse:
    return repo.update_main_plot(payload)


@router.post("/main-plot/generate", response_model=MainPlotResponse)
async def generate_main_plot(
    payload: AiGenerateSettingRequest,
    svc: SettingGeneratorService = Depends(get_setting_generator),
) -> MainPlotResponse:
    return await svc.generate_main_plot(instruction=payload.instruction)
