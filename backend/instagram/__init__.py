"""
Instagram: the assistant answers DMs to a business's Instagram account the way a person at the business would, and the team reads and
replies in the dashboard's Instagram Inbox and Live chat (instagram_plan.md, phase 5). Built like WhatsApp (whatsapp/), with Instagram's rules.

  webhook.py   Meta's callback (GET check, POST DMs) and its removal callbacks   inbound.py   keeping what Meta sends
  replies.py   when and how the assistant answers                              understand.py photos, voice messages, PDFs
  outbound.py  sending (assistant and team), and recognising Meta's echoes     graph.py     Instagram's APIs
  chats.py     who someone is, their chat and Instagram's windows             accounts.py  connecting, tokens, the assistant
  contacts.py  someone who writes is a lead; a number they give joins them up  settings.py  how the assistant behaves
  live.py      live updates for the Inbox                                      api.py       the dashboard's Instagram section
"""
