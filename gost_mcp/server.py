import logging
import asyncio
import json
from contextlib import suppress
from pathlib import Path
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP
import sys

sys.path.append(str(Path(__file__).parent.parent))
from doc_parser.docx_ast_parser import DocxASTParser, ast_to_dict

# --- Конфигурация ---
WORKSPACE_DIR = Path("./workspace")
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTS = {".docx", ".xlsx", ".xls", ".pdf"}
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 МБ

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Утилиты ---
def safe_filename(filename: str) -> Path:
    """Возвращает безопасный путь к файлу в рабочей директории (защита от Directory Traversal)."""
    return WORKSPACE_DIR / Path(filename).name

# --- MCP Server ---
mcp = FastMCP("GOST Doc Parser")

@mcp.tool(
    name="list_workspace_files",
    description="List all files in the workspace directory. Returns a list of files with their names, sizes, and types (docx, excel, json). Use this to see available documents before parsing.",
)
async def list_workspace_files() -> list[dict]:
    """List all files in the workspace directory with metadata."""
    files = []
    if not WORKSPACE_DIR.exists():
        return files
        
    for p in sorted(WORKSPACE_DIR.iterdir()):
        if not p.is_file():
            continue
        with suppress(OSError):
            st = await asyncio.to_thread(p.stat)
            files.append({
                "name": p.name,
                "size": st.st_size,
                "is_docx": p.suffix.lower() == ".docx",
                "is_excel": p.suffix.lower() in (".xlsx", ".xls"),
                "is_json": p.suffix.lower() == ".json",
            })
    
    logger.info(f"Listed {len(files)} files in workspace")
    return files

@mcp.tool(
    name="parse_document_file",
    description="Parse a DOCX file with the project AST parser and save the JSON document tree to the workspace directory. Returns the name of the saved JSON file.",
)
async def parse_document_file(file_path: str) -> str:
    """Parse a .docx file into the project's AST and save it as a JSON file in the workspace."""
    path = Path(file_path).expanduser()
    
    if not path.is_absolute():
        path = WORKSPACE_DIR / path
        
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() != ".docx":
        raise ValueError(f"Unsupported file format: {path.suffix or 'no extension'}; only .docx is supported")

    parser = DocxASTParser(str(path))
    ast_tree = parser.parse()
    ast_dict = ast_to_dict(ast_tree)
    
    json_filename = f"{path.stem}_ast.json"
    json_path = WORKSPACE_DIR / json_filename
    
    def _write_json_to_disk():
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(ast_dict, f, ensure_ascii=False, indent=2)

    await asyncio.to_thread(_write_json_to_disk)
    
    logger.info(f"Parsed and saved AST: {json_filename}")
    return f"Документ успешно распарсен. AST сохранен в файл: {json_filename}"

# Монтирование MCP
mcp_app = mcp.http_app(path='/mcp')

# --- FastAPI App ---
app = FastAPI(
    title="Doc Check MCP Server",
    lifespan=mcp_app.lifespan
)

app.mount("/gost", mcp_app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REST API ---
@app.get("/api/health")
async def health():
    return {"status": "ok", "workspace": str(WORKSPACE_DIR)}

@app.get("/api/files")
async def list_files():
    files = []
    if not WORKSPACE_DIR.exists():
        return {"files": files}
        
    for p in sorted(WORKSPACE_DIR.iterdir()):
        if not p.is_file():
            continue
        with suppress(OSError):
            st = await asyncio.to_thread(p.stat)
            files.append({
                "name": p.name,
                "size": st.st_size,
                "is_docx": p.suffix.lower() == ".docx",
                "is_excel": p.suffix.lower() in (".xlsx", ".xls"),
                "is_json": p.suffix.lower() == ".json",
            })
    return {"files": files}

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "Имя файла отсутствует")
        
    target = safe_filename(file.filename)
    
    if target.suffix.lower() not in ALLOWED_EXTS:
        raise HTTPException(400, f"Недопустимый тип файла. Разрешены: {', '.join(ALLOWED_EXTS)}")
        
    size = getattr(file, "size", None)
    if size is not None and size > MAX_UPLOAD_SIZE:
        raise HTTPException(413, "Файл слишком большой")
        
    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, "Файл слишком большой")
        
    await asyncio.to_thread(target.write_bytes, data)
    logger.info(f"Uploaded: {target.name} ({len(data)} bytes)")
    
    return {"ok": True, "name": target.name, "size": len(data)}

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    target = safe_filename(filename)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "Файл не найден")
        
    if target.suffix.lower() == ".docx":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif target.suffix.lower() in (".xlsx", ".xls"):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif target.suffix.lower() == ".json":
        media_type = "application/json"
    else:
        media_type = "application/octet-stream"
        
    return FileResponse(target, filename=target.name, media_type=media_type)

@app.delete("/api/files/{filename}")
async def delete_file(filename: str):
    target = safe_filename(filename)
    if not target.exists():
        raise HTTPException(404, "Файл не найден")
        
    await asyncio.to_thread(target.unlink)
    logger.info(f"Deleted: {target.name}")
    
    return {"ok": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)