"""
WhatsApp: the assistant answers customers on a business's WhatsApp number, the way a person at the business would,
and the team reads and replies in the dashboard's WhatsApp Inbox.

  webhook.py     Meta's callback (GET check, POST messages and receipts)    inbound.py   keeping what Meta sends
  replies.py     when and how the assistant answers                         understand.py voice notes, photos, PDFs
  outbound.py    sending (assistant and team) and keeping what was sent     graph.py     Meta's Cloud API
  chats.py       who a customer is, their chat and the 24-hour window       memory.py    shared with phone calls
  numbers.py     connected numbers and Meta's signatures                    settings.py  how the assistant behaves
  storage.py     files (the business's, and customers')                     live.py      live updates for the Inbox
  api.py         the dashboard's WhatsApp section
"""
