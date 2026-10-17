"""ISO country reference data + per-country region hints."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Country:
    name: str
    iso: str          # ISO 3166-1 alpha-2 (lower-case)
    dial: str         # calling code
    lang: str         # default Places language code
    states: Tuple[str, ...] = field(default=())
    aliases: Tuple[str, ...] = field(default=())

    @property
    def google_gl(self) -> str:
        return self.iso.upper()

    @property
    def region_code(self) -> str:
        return self.iso.upper()

    def label(self) -> str:
        return f"{self.name}  ({self.dial})"

    def search(self) -> str:
        return (self.name + " " + self.iso + " " + " ".join(self.aliases)).lower()


_US = (
    "California", "New York", "Texas", "Florida", "Illinois", "Pennsylvania", "Ohio",
    "Georgia", "North Carolina", "Michigan", "New Jersey", "Virginia", "Washington",
    "Arizona", "Massachusetts", "Tennessee", "Indiana", "Missouri", "Maryland",
    "Wisconsin", "Colorado", "Minnesota", "South Carolina", "Alabama", "Louisiana",
    "Kentucky", "Oregon", "Oklahoma", "Connecticut", "Utah", "Iowa", "Nevada",
    "Arkansas", "Mississippi", "Kansas", "New Mexico", "Nebraska", "Idaho", "West Virginia",
    "Hawaii", "New Hampshire", "Maine", "Montana", "Rhode Island", "Delaware",
    "South Dakota", "North Dakota", "Alaska", "Vermont", "Wyoming", "District of Columbia",
)

COUNTRIES: Tuple[Country, ...] = (
    Country("United States", "us", "+1", "en", _US, ("usa", "america", "u s", "united states of america")),
    Country("Canada", "ca", "+1", "en", ("Alberta", "British Columbia", "Manitoba", "New Brunswick",
          "Newfoundland and Labrador", "Nova Scotia", "Ontario", "Prince Edward Island",
          "Quebec", "Saskatchewan"), ("canada",)),
    Country("United Kingdom", "gb", "+44", "en",
            ("England", "Scotland", "Wales", "Northern Ireland", "Greater London"),
            ("uk", "britain", "great britain", "england")),
    Country("Ireland", "ie", "+353", "en", ("Leinster", "Munster", "Connacht", "Ulster"), ("eire",)),
    Country("Australia", "au", "+61", "en",
            ("New South Wales", "Victoria", "Queensland", "Western Australia",
             "South Australia", "Tasmania", "Northern Territory", "ACT"), ("aus",)),
    Country("New Zealand", "nz", "+64", "en",
            ("Auckland", "Wellington", "Canterbury", "Otago", "Waikato"), ("nz",)),
    Country("Germany", "de", "+49", "de",
            ("Bayern", "Berlin", "Nordrhein-Westfalen", "Baden-Württemberg", "Niedersachsen",
             "Hessen", "Sachsen", "Hamburg", "Schleswig-Holstein"), ("deutschland", "de")),
    Country("France", "fr", "+33", "fr",
            ("Île-de-France", "Occitanie", "Grand Est", "Nouvelle-Aquitaine", "Provence-Alpes-Côte d'Azur",
             "Hauts-de-France", "Auvergne-Rhône-Alpes"), ("france",)),
    Country("Spain", "es", "+34", "es",
            ("Madrid", "Cataluña", "Andalucía", "Valencia", "Galicia", "País Vasco", "Aragón"), ("españa", "spain")),
    Country("Portugal", "pt", "+351", "pt",
            ("Lisboa", "Porto", "Faro", "Braga", "Coimbra"), ("portugal",)),
    Country("Italy", "it", "+39", "it",
            ("Lombardia", "Lazio", "Campania", "Sicilia", "Veneto", "Piemonte", "Toscana"), ("italia",)),
    Country("Netherlands", "nl", "+31", "nl",
            ("Noord-Holland", "Zuid-Holland", "Utrecht", "Gelderland", "Overijssel", "Friesland"), ("nederland", "holland")),
    Country("Belgium", "be", "+32", "fr", ("Vlaanderen", "Wallonia", "Brussels"), ("belgië", "belgium")),
    Country("Luxembourg", "lu", "+352", "fr", ()),
    Country("Switzerland", "ch", "+41", "de", ("Zürich", "Genève", "Basel", "Bern", " Vaud"), ("schweiz",)),
    Country("Austria", "at", "+43", "de", ("Wien", "Salzburg", "Tirol", "Steiermark", "Kärnten"), ("österreich",)),
    Country("Poland", "pl", "+48", "pl", ("Mazowieckie", "Małopolskie", "Śląskie", "Pomorskie", "Wielkopolskie", "Dolnośląskie"), ("polska",)),
    Country("Sweden", "se", "+46", "sv", ("Stockholm", "Västra Götaland", "Skåne", "Uppsala"), ("sverige",)),
    Country("Norway", "no", "+47", "nb", ("Oslo", "Vestland", "Innlandet", "Trøndelag"), ("norge",)),
    Country("Denmark", "dk", "+45", "da", ("Hovedstaden", "Midtjylland", "Sjælland", "Nordjylland"), ("danmark",)),
    Country("Finland", "fi", "+358", "fi", ("Uusimaa", "Pirkanmaa", "Varsinais-Suomi", "Pohjois-Pohjanmaa"), ("suomi",)),
    Country("Isle of Man", "im", "+44", "en", (), ("isle of man",)),
    Country("Greece", "gr", "+30", "el", ("Attica", "Thessaloniki", "Crete", "Patra"), ("ελλάδα",)),
    Country("Czechia", "cz", "+420", "cs", ("Praha", "Jihomoravský", "Moravskoslezský"), ("czech republic",)),
    Country("Romania", "ro", "+40", "ro", ("București", "Cluj", "Timiș", "Iași"), ("românia",)),
    Country("Hungary", "hu", "+36", "hu", ("Budapest", "Baranya", "Borsod"), ("magyarország",)),
    Country("Brazil", "br", "+55", "pt",
            ("São Paulo", "Rio de Janeiro", "Minas Gerais", "Bahia", "Paraná", "Rio Grande do Sul",
             "Santa Catarina", "Distrito Federal", "Goiás", "Pernambuco"), ("brasil",)),
    Country("Mexico", "mx", "+52", "es",
            ("Ciudad de México", "Jalisco", "Nuevo León", "Puebla", "Yucatán", "Quintana Roo",
             "Baja California", "Veracruz", "Querétaro"), ("méxico",)),
    Country("Argentina", "ar", "+54", "es",
            ("Buenos Aires", "Córdoba", "Santa Fe", "Mendoza", "Tucumán"), ("argentina",)),
    Country("Colombia", "co", "+57", "es", ("Bogotá", "Antioquia", "Valle del Cauca", "Santander", "Cundinamarca"), ("colombia",)),
    Country("Chile", "cl", "+56", "es", ("Santiago", "Valparaíso", "Biobío", "Maule"), ("chile",)),
    Country("Peru", "pe", "+51", "es", ("Lima", "Arequipa", "Cusco", "La Libertad"), ("perú",)),
    Country("United Arab Emirates", "ae", "+971", "ar", ("Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah"), ("uae", "emirates")),
    Country("Saudi Arabia", "sa", "+966", "ar", ("Riyadh", "Jeddah", "Dammam", "Makkah"), ("ksa",)),
    Country("Qatar", "qa", "+974", "ar", ("Doha", "Al Rayyan", "Al Wakrah"), ("qatar",)),
    Country("Kuwait", "kw", "+965", "ar", ("Kuwait City", "Hawalli", "Salmiya"), ()),
    Country("Oman", "om", "+968", "ar", ("Muscat", "Salalah", "Sohar"), ()),
    Country("Israel", "il", "+972", "he", ("Tel Aviv", "Jerusalem", "Haifa", "Beersheba"), ()),
    Country("Turkey", "tr", "+90", "tr", ("İstanbul", "Ankara", "İzmir", "Antalya"), ("türkiye", "turkiye")),
    Country("Egypt", "eg", "+20", "ar", ("Cairo", "Alexandria", "Giza", "Luxor"), ()),
    Country("Morocco", "ma", "+212", "fr", ("Casablanca", "Rabat", "Marrakech", "Fès"), ()),
    Country("Tunisia", "tn", "+216", "fr", ("Tunis", "Sousse", "Sfax"), ()),
    Country("South Africa", "za", "+27", "en",
            ("Gauteng", "Western Cape", "KwaZulu-Natal", "Eastern Cape", "Kleinmond"), ("south africa",)),
    Country("Nigeria", "ng", "+234", "en", ("Lagos", "Abuja", "Port Harcourt", "Kano", "Ibadan"), ("nigeria",)),
    Country("Kenya", "ke", "+254", "en", ("Nairobi", "Mombasa", "Kisumu", "Nakuru"), ()),
    Country("Ghana", "gh", "+233", "en", ("Accra", "Kumasi", "Tamale"), ()),
    Country("Tanzania", "tz", "+255", "en", ("Dar es Salaam", "Arusha", "Mwanza"), ()),
    Country("Uganda", "ug", "+256", "en", ("Kampala", "Entebbe", "Jinja", "Mbarara"), ()),
    Country("India", "in", "+91", "en",
            ("Maharashtra", "Karnataka", "Delhi", "Telangana", "Tamil Nadu", "Gujarat", "Uttar Pradesh",
             "West Bengal", "Rajasthan", "Punjab", "Kerala", "Madhya Pradesh", "Haryana"),
            ("india", "bharat", "भारत")),
    Country("Pakistan", "pk", "+92", "en", ("Karachi", "Lahore", "Islamabad", "Faisalabad", "Rawalpindi"), ()),
    Country("Bangladesh", "bd", "+880", "en", ("Dhaka", "Chattogram", "Sylhet", "Khulna"), ()),
    Country("Sri Lanka", "lk", "+94", "en", ("Colombo", "Kandy", "Galle", "Jaffna"), ()),
    Country("Indonesia", "id", "+62", "id",
            ("Jakarta", "Surabaya", "Bandung", "Medan", "Denpasar", "Semarang"), ("indonesia",)),
    Country("Malaysia", "my", "+60", "ms", ("Kuala Lumpur", "Selangor", "Penang", "Johor Bahru", "Perak"), ("malaysia",)),
    Country("Singapore", "sg", "+65", "en", ("Central", "East", "West", "North"), ("singapore",)),
    Country("Thailand", "th", "+66", "th", ("Bangkok", "Chiang Mai", "Phuket", "Pattaya", "Chonburi"), ("thailand",)),
    Country("Vietnam", "vn", "+84", "vi", ("Hà Nội", "Hồ Chí Minh", "Đà Nẵng", "Hải Phòng"), ()),
    Country("Philippines", "ph", "+63", "en",
            ("Metro Manila", "Cebu", "Davao", "Pampanga", "Laguna", "Cavite"), ("philippines",)),
    Country("Hong Kong", "hk", "+852", "zh", ("Hong Kong Island", "Kowloon", "New Territories"), ()),
    Country("Taiwan", "tw", "+886", "zh", ("Taipei", "Kaohsiung", "Taichung", "Tainan"), ()),
    Country("Japan", "jp", "+81", "ja", ("Tokyo", "Osaka", "Yokohama", "Nagoya", "Fukuoka", "Sapporo"), ("japan",)),
    Country("South Korea", "kr", "+82", "ko", ("Seoul", "Busan", "Incheon", "Daegu", "Gyeonggi"), ("korea", "republic of korea")),
    Country("Ukraine", "ua", "+380", "uk", ("Kyiv", "Lviv", "Odesa", "Kharkiv"), ("україна",)),
    Country("Kazakhstan", "kz", "+7", "ru", ("Almaty", "Astana", "Shymkent"), ()),
    Country("Russia", "ru", "+7", "ru", ("Moscow", "Saint Petersburg", "Novosibirsk", "Kazan"), ("россия",)),
)

BY_ISO: Dict[str, Country] = {c.iso: c for c in COUNTRIES}
BY_NAME: Dict[str, Country] = {c.name.lower(): c for c in COUNTRIES}
for _c in COUNTRIES:
    BY_NAME[_c.iso] = _c
    for _a in _c.aliases:
        BY_NAME.setdefault(_a, _c)
del _c


def find(term: str) -> List[Country]:
    """Resolve a free-text country (name, iso code or alias)."""
    t = (term or "").strip().lower()
    if not t:
        return []
    if t in BY_NAME:
        return [BY_NAME[t]]
    if t in BY_ISO:
        return [BY_ISO[t]]
    return [c for c in COUNTRIES if t in c.search()]