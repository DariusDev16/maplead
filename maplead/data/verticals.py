"""Local-business vertical catalogue: search phrases + query-expansion synonyms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Vertical:
    key: str
    label: str
    query: str                       # the phrase used in " <query> in <city> "
    group: str
    synonyms: Tuple[str, ...] = ()   # extra phrases to widen the net
    tips: str = ""


def _v(key, label, query, group, syn=(), tips="") -> Vertical:
    return Vertical(key, label, query, group, tuple(syn), tips)


VERTICALS: Tuple[Vertical, ...] = (
    # ---- home services -----------------------------------------------------
    _v("plumber", "Plumber", "plumber", "Home services",
       ("plumbing company", "emergency plumber", "residential plumber")),
    _v("electrician", "Electrician", "electrician", "Home services",
       ("electrical contractor", "electrician near me")),
    _v("hvac", "HVAC / AC repair", "air conditioning repair", "Home services",
       ("hvac contractor", "heating and cooling service", "furnace repair", "ac service")),
    _v("roofer", "Roofer", "roofing contractor", "Home services",
       ("roofer", "roof repair", "roofing company")),
    _v("cleaning", "Cleaning service", "house cleaning service", "Home services",
       ("cleaners", "maid service", "commercial cleaning company")),
    _v("pest_control", "Pest control", "pest control service", "Home services",
       ("exterminator", "termite control")),
    _v("mover", "Moving company", "moving company", "Home services",
       ("movers", "removal service")),
    _v("locksmith", "Locksmith", "locksmith", "Home services", ("emergency locksmith",)),
    _v("painter", "Painter / decorator", "painting contractor", "Home services",
       ("house painter", "decorating company")),
    _v("landscaping", "Landscaping / gardening", "landscaping service", "Home services",
       ("garden maintenance", "lawn care")),
    _v("carpenter", "Carpenter / joinery", "carpenter", "Home services",
       ("joinery", "woodworking shop", "custom furniture maker")),
    _v("construction", "Construction / builder", "general contractor", "Trade",
       ("construction company", "home builder")),
    _v("interior_design", "Interior designer", "interior designer", "Trade",
       ("interior design studio",)),
    _v("architect", "Architect", "architect", "Trade", ("architecture firm",)),
    _v("solar", "Solar installer", "solar panel installer", "Trade", ("solar energy company",)),
    _v("window_door", "Window & door supplier", "window supplier", "Trade",
       ("door manufacturer", "window installer")),
    _v("flooring", "Flooring contractor", "flooring contractor", "Trade",
       ("floor installation", "carpet store")),
    _v("storage", "Storage facility", "self storage facility", "Trade",
       ("storage rental", "warehouse rental")),

    # ---- health & wellness -------------------------------------------------
    _v("dentist", "Dentist", "dentist", "Health",
       ("dental clinic", "orthodontist", "dental practice")),
    _v("doctor", "Doctor / GP clinic", "medical clinic", "Health",
       ("family doctor", "general practitioner", "health centre")),
    _v("dermatologist", "Dermatologist", "dermatologist", "Health", ("skin clinic",)),
    _v("physio", "Physiotherapist", "physiotherapist", "Health",
       ("physical therapy clinic", "rehabilitation centre")),
    _v("chiropractor", "Chiropractor", "chiropractor", "Health", ()),
    _v("optician", "Optician / eye clinic", "optician", "Health",
       ("ophthalmologist", "eye clinic")),
    _v("veterinary", "Veterinary clinic", "veterinarian", "Health",
       ("vet clinic", "animal hospital")),
    _v("pharmacy", "Pharmacy", "pharmacy", "Health", ("chemist", "drug store")),
    _v("psychologist", "Psychologist / therapist", "psychologist", "Health",
       ("therapist", "counselling centre")),
    _v("gym", "Gym / fitness studio", "gym", "Health & fitness",
       ("fitness centre", "personal trainer", "crossfit box")),
    _v("yoga", "Yoga / pilates studio", "yoga studio", "Health & fitness",
       ("pilates studio",)),
    _v("salon", "Hair salon / barber", "hair salon", "Beauty",
       ("barbershop", "beauty salon", "barber")),
    _v("spa", "Spa / massage", "spa", "Beauty", ("massage therapy", "wellness centre")),
    _v("tattoo", "Tattoo studio", "tattoo studio", "Beauty", ("tattoo parlour", "piercing studio")),
    _v("nail", "Nail salon", "nail salon", "Beauty", ("manicure salon",)),

    # ---- professional services --------------------------------------------
    _v("lawyer", "Law firm / lawyer", "law firm", "Professional",
       ("lawyer", "attorney", "solicitor")),
    _v("accountant", "Accountant / tax advisor", "accounting firm", "Professional",
       ("tax advisor", "bookkeeping service", "financial planner")),
    _v("real_estate", "Real estate agent", "real estate agency", "Real estate",
       ("realtor", "property letting agent", "estate agent")),
    _v("insurance", "Insurance agency", "insurance agency", "Professional",
       ("insurance broker",)),
    _v("bank", "Bank / credit union", "bank", "Finance",
       ("credit union", "mortgage broker")),
    _v("it_services", "IT / web agency", "it company", "Technology",
       ("web design agency", "software development company", "managed service provider")),
    _v("marketing", "Marketing / advertising agency", "marketing agency", "Technology",
       ("advertising agency", "digital marketing company", "seo agency")),
    _v("consulting", "Consulting firm", "consulting firm", "Professional",
       ("business consultant",)),
    _v("notary", "Notary / legal services", "notary", "Professional", ()),
    _v("recruitment", "Recruitment / staffing agency", "recruitment agency", "Professional",
       ("staffing agency", "headhunter", "job placement agency")),

    # ---- auto --------------------------------------------------------------
    _v("auto_repair", "Car repair / garage", "car repair", "Automotive",
       ("auto repair shop", "mechanic", "garage")),
    _v("auto_dealer", "Car dealership", "car dealership", "Automotive",
       ("used car dealer", "motorcycle dealer")),
    _v("car_wash", "Car wash / detailing", "car wash", "Automotive",
       ("car detailing", "mobile car wash")),
    _v("tire_shop", "Tire shop", "tyre shop", "Automotive", ("tire service",)),
    _v("ev_charging", "EV charging station", "electric vehicle charging station", "Automotive", ("ev charger",)),
    _v("driving_school", "Driving school", "driving school", "Automotive", ("driving instructor",)),

    # ---- food & hospitality ------------------------------------------------
    _v("restaurant", "Restaurant", "restaurant", "Food & drink",
       ("restaurant", "diner", "bistro", "eatery")),
    _v("cafe", "Cafe / coffee shop", "coffee shop", "Food & drink",
       ("cafe", "coffee roaster", "espresso bar")),
    _v("bakery", "Bakery / pastry shop", "bakery", "Food & drink", ("pastry shop", "cake shop")),
    _v("bar", "Bar / pub / nightclub", "bar", "Food & drink",
       ("pub", "cocktail bar", "nightclub")),
    _v("hotel", "Hotel / accommodation", "hotel", "Travel",
       ("hostel", "guesthouse", "motel", "bed and breakfast")),
    _v("travel_agency", "Travel agency", "travel agency", "Travel",
       ("tour operator", "holiday booking office")),
    _v("catering", "Catering / event food", "catering company", "Food & drink",
       ("event catering", "meal delivery service")),
    _v("supermarket", "Supermarket / grocery", "supermarket", "Retail",
       ("grocery store", "convenience store", "food market")),

    # ---- retail & services -------------------------------------------------
    _v("florist", "Florist", "florist", "Retail", ("flower shop",)),
    _v("jeweller", "Jeweller", "jewellery store", "Retail", ("jewelry store", "watch shop")),
    _v("furniture", "Furniture store", "furniture store", "Retail", ("home furnishing shop",)),
    _v("electronics_repair", "Electronics / phone repair", "phone repair", "Retail",
       ("electronics repair shop", "computer repair")),
    _v("photographer", "Photographer", "photographer", "Creative",
       ("photography studio", "wedding photographer")),
    _v("dry_cleaning", "Dry cleaner / laundry", "dry cleaning service", "Retail",
       ("laundry service",)),
    _v("printing", "Printing / signage shop", "printing shop", "Creative",
       ("sign maker", "screen printing")),
    _v("childcare", "Childcare / nursery", "daycare center", "Services",
       ("nursery school", "preschool", "childminder")),
    _v("tutoring", "Tutoring / academy", "tutoring center", "Education",
       ("learning center", "private teacher", "test prep center")),
    _v("school", "School / college", "school", "Education", ("private school", "college", "academy")),
    _v("coworking", "Coworking space", "coworking space", "Services", ("office rental", "shared office")),
)

BY_KEY: Dict[str, Vertical] = {v.key: v for v in VERTICALS}

GROUPS: Tuple[str, ...] = tuple(dict.fromkeys(v.group for v in VERTICALS))


def resolve(term: str) -> List[Vertical]:
    """Resolve free text to verticals (label / key / synonym substring)."""
    t = (term or "").strip().lower()
    if not t:
        return []
    if t in BY_KEY:
        return [BY_KEY[t]]
    hits = [v for v in VERTICALS
            if t == v.key or t in v.key or t in v.label.lower()
            or any(t in s for s in v.synonyms) or t in v.query]
    return hits