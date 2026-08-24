from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from app.api.dependencies import get_container
from app.container import Container

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/bangumi")
async def bangumi_image(
    request: Request,
    url: Annotated[str, Query(max_length=2048)],
    container: Annotated[Container, Depends(get_container)],
) -> Response:
    image = await container.image_proxy.get(url)
    return Response(
        content=image.content,
        media_type=image.media_type,
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )
