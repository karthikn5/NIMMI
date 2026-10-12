"""
Ready-made starting points by industry: the assistant's instructions, a starter
knowledge sheet to fill in, and its voice goal and fields to collect.
Text in [brackets] is for the business to replace.
"""


def _f(label, type_="text", description="", required=False, choices=None):
    key = "".join(c if c.isalnum() else "_" for c in label.lower()).strip("_")
    return {"key": key, "label": label, "type": type_, "description": description, "choices": choices or [], "required": required}


TEMPLATES = [
    {
        "id": "real_estate", "name": "Real estate", "summary": "Answer project questions and book site visits.",
        "prompt": ("You help buyers with questions about our projects: locations, unit sizes, prices, amenities, loans and possession dates. "
                   "Be warm and specific. When someone is interested, offer a site visit and collect their name, phone number, "
                   "budget and preferred visit time."),
        "knowledge": ("Projects: [Project name, location, unit types like 2BHK and 3BHK, price range]\n"
                      "Amenities: [Clubhouse, pool, parking...]\nPossession: [Month and year]\n"
                      "Home loans: [Partner banks]\nSite visits: [Days and times, meeting point]\nOffice: [Address, phone, hours]"),
        "greeting": "Are you looking for a home with us?",
        "goal": "The caller books a site visit or asks for a call from the sales team.",
        "fields": [_f("Name", required=True), _f("Phone number", "phone", required=True), _f("Budget", "number", "In lakhs"),
                   _f("Unit type", "choice", choices=["1BHK", "2BHK", "3BHK", "Villa", "Plot"]), _f("Visit date", "date", "When they'd like to visit")],
    },
    {
        "id": "education", "name": "Coaching and colleges", "summary": "Admissions questions, fees and counselling calls.",
        "prompt": ("You answer questions about our courses, eligibility, fees, batches, scholarships and placements. "
                   "Encourage serious students to book a free counselling session, and collect their name, phone number, "
                   "course of interest and current qualification."),
        "knowledge": ("Courses: [Course name, duration, mode online or classroom]\nEligibility: [Minimum qualification]\n"
                      "Fees: [Per course, instalments, scholarships]\nNext batch: [Start dates]\nPlacements: [Highlights]\n"
                      "Campus: [Address, timings, phone]"),
        "greeting": "Are you asking about admissions?",
        "goal": "The student books a counselling session or applies.",
        "fields": [_f("Name", required=True), _f("Phone number", "phone", required=True), _f("Course", "text", "Course they're interested in", True),
                   _f("Qualification", "text", "Current or last completed"), _f("City")],
    },
    {
        "id": "clinic", "name": "Clinic or hospital", "summary": "Doctor timings, services and appointments.",
        "prompt": ("You help patients with doctor availability, departments, consultation fees, timings and directions. "
                   "Never give medical advice or diagnoses; for anything medical, suggest booking a consultation, and for emergencies "
                   "tell them to call [emergency number] or go to the nearest emergency room. Collect the patient's name, phone number "
                   "and preferred appointment time."),
        "knowledge": ("Doctors: [Name, specialty, days and times]\nConsultation fee: [Amount]\nServices: [Lab tests, scans...]\n"
                      "Insurance: [Accepted insurers]\nEmergency: [24x7 number]\nAddress: [Address, parking, landmarks]"),
        "greeting": "Would you like to book an appointment?",
        "goal": "The caller books or confirms an appointment.",
        "fields": [_f("Patient name", required=True), _f("Phone number", "phone", required=True), _f("Department"),
                   _f("Preferred date", "date"), _f("First visit", "yes_no", "Whether they've visited before")],
    },
    {
        "id": "restaurant", "name": "Restaurant", "summary": "Menu, timings, table bookings and orders.",
        "prompt": ("You answer questions about our menu, prices, timings, location and offers, and take table bookings. "
                   "For bookings, collect the name, phone number, number of guests, date and time."),
        "knowledge": ("Menu highlights: [Dishes and prices]\nVeg / Jain options: [Yes or no, details]\nTimings: [Lunch and dinner]\n"
                      "Delivery: [Swiggy, Zomato, own delivery area]\nParking: [Details]\nAddress: [Address, landmark]"),
        "greeting": "Would you like to book a table?",
        "goal": "The caller books a table.",
        "fields": [_f("Name", required=True), _f("Phone number", "phone", required=True), _f("Guests", "number", "How many people", True),
                   _f("Date and time", "text", "When they want the table", True)],
    },
    {
        "id": "ecommerce", "name": "Online store (D2C)", "summary": "Orders, delivery, returns and COD confirmation.",
        "prompt": ("You help shoppers with products, sizes, delivery times, cash on delivery, returns and refunds. "
                   "Be friendly and brief. For order problems, collect the order ID and phone number so the team can help."),
        "knowledge": ("Shipping: [Delivery time by city, charges]\nCash on delivery: [Available or not, limits]\n"
                      "Returns: [Window, condition, how to start]\nRefunds: [How long, to which method]\n"
                      "Sizes: [Size guide link or table]\nSupport: [Email, WhatsApp, hours]"),
        "greeting": "Are you calling about an order?",
        "goal": "The customer's question is answered, or a COD order is confirmed.",
        "fields": [_f("Name"), _f("Order ID", "text", "Order number", True), _f("Phone number", "phone"),
                   _f("Order confirmed", "yes_no", "Whether they confirmed the cash-on-delivery order")],
    },
    {
        "id": "salon", "name": "Salon and spa", "summary": "Services, prices and appointment bookings.",
        "prompt": ("You answer questions about our services, prices, stylists and timings, and book appointments. "
                   "Collect the name, phone number, service and preferred time."),
        "knowledge": ("Services and prices: [Haircut, colour, facial, spa...]\nStylists: [Names, specialties]\n"
                      "Timings: [Open hours, days]\nOffers: [Current packages]\nAddress: [Address, landmark]"),
        "greeting": "Would you like to book an appointment?",
        "goal": "The caller books an appointment.",
        "fields": [_f("Name", required=True), _f("Phone number", "phone", required=True), _f("Service", required=True),
                   _f("Preferred time", "text", "Day and time")],
    },
    {
        "id": "travel", "name": "Travel agency", "summary": "Packages, visas and trip enquiries.",
        "prompt": ("You help travellers with holiday packages, prices, inclusions, visas and dates. "
                   "For interested travellers, collect the name, phone number, destination, travel dates and number of people."),
        "knowledge": ("Packages: [Destination, nights, price per person, inclusions]\nVisa help: [Countries, documents, time]\n"
                      "Payment: [Booking amount, EMI options]\nCancellation: [Policy]\nOffice: [Address, phone, hours]"),
        "greeting": "Where would you like to travel?",
        "goal": "The traveller asks for a quote or books a package.",
        "fields": [_f("Name", required=True), _f("Phone number", "phone", required=True), _f("Destination", required=True),
                   _f("Travel dates"), _f("Travellers", "number", "Number of people"), _f("Budget", "number", "Per person, in rupees")],
    },
    {
        "id": "finance", "name": "Insurance and loans", "summary": "Plan questions and lead qualification.",
        "prompt": ("You explain our insurance plans or loan products in simple language and help people find a fit. "
                   "Never promise approval, returns or guaranteed amounts; say a licensed advisor will confirm. "
                   "Collect the name, phone number, product interest, age and city."),
        "knowledge": ("Products: [Plan or loan names, key features]\nEligibility: [Age, income, documents]\n"
                      "Rates or premiums: [Starting from, what changes it]\nClaims / disbursal: [Process and time]\n"
                      "Regulator details: [IRDAI / RBI registration number]\nContact: [Phone, branch hours]"),
        "greeting": "Are you looking for a plan or a loan?",
        "goal": "The person agrees to a call from a licensed advisor.",
        "fields": [_f("Name", required=True), _f("Phone number", "phone", required=True),
                   _f("Interested in", "choice", choices=["Health insurance", "Life insurance", "Motor insurance", "Home loan", "Personal loan", "Business loan"]),
                   _f("Age", "number"), _f("City"), _f("Monthly income", "number", "In rupees")],
    },
]
BY_ID = {t["id"]: t for t in TEMPLATES}


def catalog() -> list[dict]:
    return [{"id": t["id"], "name": t["name"], "summary": t["summary"],
             "fields": [f["label"] for f in t["fields"]], "goal": t["goal"]} for t in TEMPLATES]
