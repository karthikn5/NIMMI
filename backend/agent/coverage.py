"""
"Everything I can do in the dashboard, Nimmi can do": which API routes the agent's tools do the work of (each tool
lists its `routes`), which it never will and why (EXCLUDED), and which it should and doesn't yet (PENDING, with the
phase that adds them; NIMMI_AGENT_PLAN.md). tests/test_agent.py checks every route of the app is in exactly one
place, so a new feature can't be forgotten: give it a tool, or say here why not.

Keys: "METHOD /path" for one route; a path ending in "/" for every route under it.
"""
EXCLUDED = {
    "GET /": "a server check", "GET /api/test": "a server check", "GET /api/health": "a server check",
    "/api/auth/": "signing in, passwords and the person's own account: they do these themselves",
    "/api/payments/": "paying: the agent opens Billing and the person pays there",
    "/api/chat/": "the chat widget's own API, used by website visitors, not the dashboard",
    "/api/agent/": "the agent's own API",
    "GET /mcp": "the MCP endpoint itself (agent/mcp.py)", "POST /mcp": "the MCP endpoint itself (agent/mcp.py)",
    "/api/voice/twilio/": "calls from the phone company", "/api/voice/exotel/": "calls from the phone company",
    "GET /api/integrations/whatsapp/webhook": "Meta's check of the webhook",
    "POST /api/integrations/whatsapp/webhook": "messages from WhatsApp (Meta)",
    "POST /api/sites/hooks/{secret}": "deploys started by a Git service",
    "POST /api/voice/admin/numbers/{number_id}/activate": "Nimmi's own staff",
    "POST /api/sites/admin/{slug}/{action}": "Nimmi's own staff",
    "POST /api/team/accept": "accepting an invitation: the invited person does it",
    "GET /api/team/workspaces": "switching workspace: the menu at the top right",
    "GET /api/integrations/email/unsubscribe": "the unsubscribe link in emails (public)",
    "POST /api/integrations/email/unsubscribe": "the unsubscribe link in emails (public)",
    "POST /api/voice/session": "a test call in the browser: the person talks; the agent opens the page",
    "POST /api/voice/test-call": "Call me rings the person's own phone: they start it themselves",
    "GET /api/voice/calls/{call_id}/recording": "audio for the page's player",
    "GET /api/whatsapp/media/{ref}": "photos and files for the page to show",
    "GET /api/voice/voices/{voice_id}/sample": "audio for the page's Play button",
    "GET /api/voice/ambience/{kind}/sample": "audio for the page's Play button",
    "POST /api/bots/{bot_id}/logo": "uploading a picture: the person picks the file",
    "POST /api/bots/{bot_id}/background": "uploading a picture: the person picks the file",
    "POST /api/bots/{bot_id}/knowledge/upload": "uploading a document: the person picks the file",
    "POST /api/whatsapp/files": "uploading a file: the person picks it",
    "POST /api/voice/numbers/{number_id}/documents": "uploading business documents: the person picks them",
    "POST /api/sites/{site_id}/deploys": "uploading a website: the person picks the files",
    "POST /api/voice/numbers/buy": "buying a number: the agent opens Numbers and the person pays there",
    "POST /api/voice/numbers": "asking for a paid number: the person does it on Numbers",
    "POST /api/voice/numbers/{number_id}/replace": "a paid replacement number: the person does it on Numbers",
    "DELETE /api/voice/numbers/{number_id}": "giving up a paid number: the person does it on Numbers",
    "GET /api/voice/numbers/available": "numbers for sale: part of buying, on Numbers",
    "GET /api/voice/packs": "credit packs for sale: part of buying, on Billing",
    "POST /api/voice/phone-accounts": "connecting a Twilio or Exotel account needs its secret token: it goes in the "
                                      "form, never through the agent",
    "POST /api/whatsapp/numbers": "connecting WhatsApp needs a token and app secret: they go in the form, never "
                                  "through the agent",
    "POST /api/bots/{bot_id}/knowledge/reindex": "the search index rebuilds by itself after every knowledge change",
    "POST /api/bots/{bot_id}/knowledge/summary": "the business summary rewrites itself after every knowledge change",
    "POST /api/handoffs/{conversation_id}/reply": "replying to a customer is the team's job: the agent opens the chat",
    "POST /api/whatsapp/chats/{chat_id}/send": "replying to a customer is the team's job: the agent opens the chat",
    "POST /api/voice/callbacks/request": "a visitor asking for a call (the chat widget)",
}

PENDING = {
    # Phase 3: "create an agent for me"
    "POST /api/knowledge/youtube": "phase 3: knowledge from a video",
    "POST /api/voice/scripts/{bot_id}/{direction}/draft": "phase 3: the voice script written with AI",
    "GET /api/bots/{bot_id}/install": "phase 3: the install code", "POST /api/bots/export": "phase 3: the install code",
    "GET /api/bots/{bot_id}/wordpress-plugin": "phase 3: the install code",
    # Phase 4: phone numbers, WhatsApp and Cal.com, guided
    "GET /api/voice/numbers/countries": "phase 4: numbers",
    "PATCH /api/voice/phone-accounts/{account_id}": "phase 4: phone accounts",
    "DELETE /api/voice/phone-accounts/{account_id}": "phase 4: phone accounts",
    "GET /api/voice/phone-accounts/{account_id}/numbers": "phase 4: phone accounts",
    "POST /api/voice/phone-accounts/{account_id}/numbers": "phase 4: phone accounts",
    "DELETE /api/whatsapp/numbers/{number_id}": "phase 4: WhatsApp numbers",
    "POST /api/whatsapp/numbers/{number_id}/refresh": "phase 4: WhatsApp numbers",
    "POST /api/whatsapp/numbers/{number_id}/test": "phase 4: WhatsApp numbers",
    "POST /api/voice/agents/{bot_id}/functions/test": "phase 4: functions (Cal.com)",
    # Phase 5: the rest of the dashboard
    "GET /api/usage": "phase 5", "GET /api/billing/balance": "phase 5: billing (owners)",
    "GET /api/handoffs/{conversation_id}/messages": "phase 5: live chat", "POST /api/handoffs/{conversation_id}/accept": "phase 5: live chat",
    "POST /api/handoffs/{conversation_id}/close": "phase 5: live chat", "POST /api/handoffs/{conversation_id}/notes": "phase 5: live chat",
    "GET /api/integrations": "phase 5: integrations", "PUT /api/integrations": "phase 5: integrations",
    "GET /api/integrations/log": "phase 5: integrations", "POST /api/integrations/test": "phase 5: integrations",
    "POST /api/integrations/google-sheets": "phase 5: integrations",
    "POST /api/integrations/email/audience": "phase 5: email", "GET /api/integrations/email/broadcasts": "phase 5: email",
    "POST /api/integrations/email/broadcasts": "phase 5: email (confirm level)",
    "POST /api/integrations/email/broadcasts/{broadcast_id}/cancel": "phase 5: email",
    "GET /api/integrations/email/history": "phase 5: email", "GET /api/integrations/email/jobs/{job_id}": "phase 5: email",
    "POST /api/integrations/email/jobs/{job_id}/cancel": "phase 5: email", "POST /api/integrations/email/jobs/{job_id}/resend": "phase 5: email",
    "POST /api/integrations/email/stop": "phase 5: email",
    "POST /api/questions": "phase 5: questions", "DELETE /api/questions/{gap_id}": "phase 5: questions", "POST /api/sites": "phase 5: deployments", "GET /api/sites/check": "phase 5: deployments",
    "GET /api/sites/{site_id}": "phase 5: deployments", "PATCH /api/sites/{site_id}": "phase 5: deployments",
    "DELETE /api/sites/{site_id}": "phase 5: deployments (confirm level)", "POST /api/sites/{site_id}/restore": "phase 5: deployments",
    "POST /api/sites/{site_id}/deploys/git": "phase 5: deployments",
    "POST /api/sites/{site_id}/deploys/{deploy_id}/promote": "phase 5: deployments (confirm level)",
    "PUT /api/sites/{site_id}/domain": "phase 5: deployments", "DELETE /api/sites/{site_id}/domain": "phase 5: deployments",
    "POST /api/sites/{site_id}/domain/check": "phase 5: deployments", "POST /api/sites/{site_id}/hook": "phase 5: deployments",
    "DELETE /api/sites/{site_id}/hook": "phase 5: deployments", "PATCH /api/team/members/{member_id}": "phase 5: team (confirm level)",
    "DELETE /api/team/members/{member_id}": "phase 5: team (confirm level)",
    "GET /api/voice/callbacks": "phase 5: call back new leads", "PUT /api/voice/callbacks": "phase 5: call back new leads",
    "GET /api/voice/callbacks/jobs": "phase 5: call back new leads", "POST /api/voice/campaigns": "phase 5: campaigns (confirm level)",
    "GET /api/voice/campaigns/{campaign_id}": "phase 5: campaigns",
    "POST /api/voice/campaigns/{campaign_id}/{action}": "phase 5: campaigns (confirm level)",
    "GET /api/voice/compliance": "phase 5: compliance", "PUT /api/voice/compliance": "phase 5: compliance",
    "GET /api/voice/dnc": "phase 5: compliance", "POST /api/voice/dnc": "phase 5: compliance",
    "DELETE /api/voice/dnc/{entry_id}": "phase 5: compliance", "POST /api/voice/erase": "phase 5: compliance (confirm level)", "GET /api/voice/contacts/{contact_id}": "phase 5: contacts",
    "PATCH /api/voice/contacts/{contact_id}": "phase 5: contacts", "POST /api/voice/contacts/{contact_id}/forget": "phase 5: contacts",
    "GET /api/voice/data": "phase 5: collected data",
    "PATCH /api/voice/schedule/contacts/{contact_id}": "phase 5: Schedule",
    "GET /api/voice/schedule/contacts/{contact_id}/next": "phase 5: Schedule",
    "GET /api/voice/schedule/free-times": "phase 5: Schedule", "GET /api/voice/schedule/hosts": "phase 5: Schedule", "POST /api/voice/schedule/items": "phase 5: Schedule (confirm level)",
    "PATCH /api/voice/schedule/items/{job_id}": "phase 5: Schedule", "POST /api/voice/schedule/items/{job_id}/{action}": "phase 5: Schedule", "GET /api/voice/schedule/meetings/{meeting_id}": "phase 5: Schedule",
    "PATCH /api/voice/schedule/meetings/{meeting_id}": "phase 5: Schedule",
    "POST /api/voice/schedule/meetings/{meeting_id}/approve": "phase 5: Schedule (confirm level)",
    "POST /api/voice/schedule/meetings/{meeting_id}/decline": "phase 5: Schedule (confirm level)",
    "POST /api/voice/schedule/meetings/{meeting_id}/mark": "phase 5: Schedule",
    "POST /api/voice/schedule/meetings/{meeting_id}/propose": "phase 5: Schedule (confirm level)", "GET /api/whatsapp/chats/{chat_id}": "phase 5: WhatsApp inbox",
    "POST /api/whatsapp/chats/{chat_id}/assign": "phase 5: WhatsApp inbox", "POST /api/whatsapp/chats/{chat_id}/notes": "phase 5: WhatsApp inbox",
    "POST /api/whatsapp/chats/{chat_id}/pause": "phase 5: WhatsApp inbox", "POST /api/whatsapp/chats/{chat_id}/resume": "phase 5: WhatsApp inbox",
    "POST /api/whatsapp/chats/{chat_id}/read": "phase 5: WhatsApp inbox", "POST /api/whatsapp/chats/{chat_id}/status": "phase 5: WhatsApp inbox",
    "GET /api/whatsapp/confirmations": "phase 5: WhatsApp", "PUT /api/whatsapp/confirmations": "phase 5: WhatsApp",
    "PATCH /api/whatsapp/files/{file_id}": "phase 5: WhatsApp files", "DELETE /api/whatsapp/files/{file_id}": "phase 5: WhatsApp files",
    "GET /api/whatsapp/files": "phase 5: WhatsApp files", "GET /api/whatsapp/people": "phase 5: WhatsApp",
    "GET /api/workspace/replies": "phase 5: saved replies", "POST /api/workspace/replies": "phase 5: saved replies",
    "PUT /api/workspace/replies/{reply_id}": "phase 5: saved replies", "DELETE /api/workspace/replies/{reply_id}": "phase 5: saved replies",
}


def place(route: str) -> list[str]:
    """Where a route ("METHOD /path") is accounted for: tool names, "excluded" and/or "pending"."""
    from agent.registry import TOOLS
    method, path = route.split(" ", 1)
    found = [f"tool {t.name}" for t in TOOLS.values() if route in t.routes]
    if route in EXCLUDED or any(key.endswith("/") and not key.startswith(("GET ", "POST ")) and path.startswith(key) for key in EXCLUDED):
        found.append("excluded")
    if route in PENDING:
        found.append("pending")
    return found
