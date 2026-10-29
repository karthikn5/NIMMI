"""Tools that move the person's screen: open a page, or point at something on it. The panel does it (a CUSTOM
event), so the person sees it happen; nothing is changed."""
from urllib.parse import urlencode

from auth import get_owned_bot
from agent import screens
from agent.registry import ToolError, tool

PAGES = screens.pages()


@tool("go_to", "Open a dashboard page for them. Pages with {assistant} in their path need assistant_id.",
      "Opening the page", {"type": "object", "required": ["page"], "properties": {
          "page": {"type": "string", "enum": sorted(PAGES)},
          "assistant_id": {"type": "string", "description": "For the builder, a voice agent or a voice script."},
          "tab": {"type": "string", "enum": ["design", "knowledge", "behaviour", "flow", "leads"], "description": "Builder only."},
          "direction": {"type": "string", "enum": ["inbound", "outbound"], "description": "Voice agent and script pages only."}}})
async def go_to(tc, db, page, assistant_id=None, tab=None, direction=None):
    path = PAGES[page]
    if "{assistant}" in path:
        if not assistant_id:
            raise ToolError(f"{screens.SCREENS[page]['title']} needs assistant_id (use list_assistants).")
        bot = await get_owned_bot(assistant_id, tc.ctx, db)
        path = path.replace("{assistant}", bot.bot_id)
    query = {k: v for k, v in (("tab", tab if page == "builder" else None),
                               ("direction", direction if page in ("voice_agent", "voice_script", "voice_agents") else None)) if v}
    if query:
        path += "?" + urlencode(query)
    tc.act("navigate", {"path": path})
    return {"opened": screens.SCREENS[page]["title"], "path": path}


@tool("point_at", "Highlight something on their screen for a few seconds, to show where to click. Use it when it's on "
      "the screen they're on (the top bar menus are on every page except the builder).", "Pointing it out",
      {"type": "object", "required": ["element"], "properties": {
          "element": {"type": "string", "enum": sorted(screens.POINTS),
                      "description": "nav.*: the top bar's menus; the others: this page's tabs and buttons."}}})
async def point_at(tc, db, element):
    tc.act("highlight", {"element": element})
    return {"pointed_at": screens.POINTS[element]}
