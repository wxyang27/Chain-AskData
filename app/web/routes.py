from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    """返回首版 Web 页面。"""

    with open("templates/index.html", "r", encoding="utf-8") as file:
        return file.read()
