"""
Nimmi, the dashboard's own agent: a panel beside every dashboard screen that knows which screen is open and works
in the person's workspace with their permissions. The plan, and what each phase adds: NIMMI_AGENT_PLAN.md.

  router.py     the API the panel uses (/api/agent): send a message, follow or replay a run, stop it, past chats
  loop.py       one run: the model, the tools it asks for, their results, the model again
  providers.py  the AI models (Gemini, OpenAI, Groq), one streaming call with tools, the next model as backup
  events.py     the run's events (AG-UI names), numbered and saved, so a reload or another process continues
  registry.py   the tools: inputs checked, errors in plain words, results clipped, secrets hidden
  prompt.py     what the model is told
  tools/        the tools themselves, grouped by part of the dashboard
"""
