"""
City catalogue - the wizard never asks "which city?" with a blank box again.

Two levels of data per country:
  * region -> cities  (offers the right list once a region is chosen)
  * country -> cities (offers the whole country when the region is unknown)

Keys are matched case-, accent- and punctuation-insensitively, so "sao paulo",
"São Paulo" and "SAO  PAULO" all hit the same entry.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple


# --------------------------------------------------------------------------- #
# region -> cities
# --------------------------------------------------------------------------- #

_REGIONS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    # ---------------- united states -------------------------------------
    "us": {
        "California": ("Los Angeles", "San Diego", "San Jose", "San Francisco",
                       "Fresno", "Sacramento", "Long Beach", "Oakland",
                       "Bakersfield", "Anaheim", "Riverside", "Irvine",
                       "Santa Ana", "Chula Vista", "Stockton", "Santa Clarita"),
        "New York": ("New York City", "Buffalo", "Rochester", "Yonkers",
                     "Syracuse", "Albany", "New Rochelle", "Mount Vernon"),
        "Texas": ("Houston", "San Antonio", "Dallas", "Austin", "Fort Worth",
                  "El Paso", "Arlington", "Corpus Christi", "Plano", "Laredo",
                  "Lubbock", "Irving"),
        "Florida": ("Jacksonville", "Miami", "Tampa", "Orlando",
                    "St. Petersburg", "Hialeah", "Tallahassee",
                    "Port St. Lucie", "Cape Coral", "Pembroke Pines", "Fort Lauderdale"),
        "Illinois": ("Chicago", "Aurora", "Joliet", "Naperville", "Rockford",
                     "Springfield", "Peoria", "Elgin", "Schaumburg"),
        "Pennsylvania": ("Philadelphia", "Pittsburgh", "Allentown", "Erie",
                         "Reading", "Harrisburg", "Bethlehem", "Lancaster"),
        "Ohio": ("Columbus", "Cleveland", "Cincinnati", "Toledo", "Akron",
                 "Dayton", "Parma", "Canton"),
        "Georgia": ("Atlanta", "Augusta", "Columbus", "Savannah", "Athens",
                    "Macon", "Roswell", "Marietta"),
        "North Carolina": ("Charlotte", "Raleigh", "Greensboro", "Durham",
                           "Winston-Salem", "Fayetteville", "Wilmington", "Asheville"),
        "Michigan": ("Detroit", "Grand Rapids", "Warren", "Sterling Heights",
                     "Ann Arbor", "Lansing", "Flint", "Traverse City"),
        "New Jersey": ("Newark", "Jersey City", "Paterson", "Elizabeth",
                       "Edison", "Woodbridge", "Camden", "Atlantic City"),
        "Virginia": ("Virginia Beach", "Norfolk", "Chesapeake", "Richmond",
                     "Newport News", "Alexandria", "Hampton", "Charlottesville"),
        "Washington": ("Seattle", "Spokane", "Tacoma", "Vancouver", "Bellevue",
                       "Kent", "Everett", "Yakima"),
        "Arizona": ("Phoenix", "Tucson", "Mesa", "Scottsdale", "Tempe",
                    "Chandler", "Glendale", "Flagstaff"),
        "Massachusetts": ("Boston", "Worcester", "Springfield", "Cambridge",
                           "Lowell", "Brockton", "Quincy", "Lynn"),
        "Tennessee": ("Nashville", "Memphis", "Knoxville", "Chattanooga",
                      "Clarksville", "Murfreesboro", "Franklin"),
        "Indiana": ("Indianapolis", "Fort Wayne", "Evansville", "South Bend",
                    "Bloomington", "Hammond", "Muncie"),
        "Missouri": ("Kansas City", "St. Louis", "Springfield", "Columbia",
                     "Independence", "Lee's Summit"),
        "Maryland": ("Baltimore", "Columbia", "Germantown", "Silver Spring",
                     "Waldorf", "Frederick", "Bethesda"),
        "Wisconsin": ("Milwaukee", "Madison", "Green Bay", "Kenosha",
                      "Racine", "Appleton", "Oshkosh"),
        "Colorado": ("Denver", "Colorado Springs", "Aurora", "Fort Collins",
                     "Lakewood", "Boulder", "Pueblo", "Grand Junction"),
        "Minnesota": ("Minneapolis", "St. Paul", "Rochester", "Duluth",
                      "Bloomington", "Brooklyn Park"),
        "South Carolina": ("Charleston", "Columbia", "North Charleston",
                           "Mount Pleasant", "Rock Hill", "Greenville"),
        "Alabama": ("Birmingham", "Montgomery", "Mobile", "Huntsville", "Tuscaloosa"),
        "Louisiana": ("New Orleans", "Baton Rouge", "Shreveport", "Lafayette",
                      "Lake Charles", "Monroe"),
        "Kentucky": ("Louisville", "Lexington", "Bowling Green", "Owensboro",
                     "Covington", "Richmond"),
        "Oregon": ("Portland", "Salem", "Eugene", "Gresham", "Hillsboro",
                   "Beaverton", "Medford"),
        "Oklahoma": ("Oklahoma City", "Tulsa", "Norman", "Broken Arrow",
                     "Edmond", "Lawton", "Enid"),
        "Connecticut": ("Bridgeport", "New Haven", "Stamford", "Hartford",
                        "Waterbury", "Norwalk"),
        "Utah": ("Salt Lake City", "West Valley City", "Provo", "West Jordan",
                 "Orem", "Ogden", "St. George"),
        "Iowa": ("Des Moines", "Cedar Rapids", "Davenport", "Sioux City",
                 "Iowa City", "Waterloo"),
        "Nevada": ("Las Vegas", "Henderson", "Reno", "North Las Vegas",
                   "Carson City", "Sparks", "Mesquite"),
        "Arkansas": ("Little Rock", "Fayetteville", "Fort Smith",
                     "Springdale", "Jonesboro", "Bentonville"),
        "Mississippi": ("Jackson", "Gulfport", "Biloxi", "Hattiesburg",
                        "Southaven", "Meridian"),
        "Kansas": ("Wichita", "Overland Park", "Kansas City", "Topeka",
                   "Lawrence", "Olathe", "Manhattan"),
        "New Mexico": ("Albuquerque", "Las Cruces", "Rio Rancho", "Santa Fe",
                       "Roswell", "Clovis"),
        "Nebraska": ("Omaha", "Lincoln", "Bellevue", "Grand Island",
                     "Kearney", "North Platte"),
        "Idaho": ("Boise", "Meridian", "Nampa", "Idaho Falls", "Pocatello",
                  "Coeur d'Alene"),
        "West Virginia": ("Charleston", "Huntington", "Morgantown",
                          "Parkersburg", "Wheeling", "Martinsburg"),
        "Hawaii": ("Honolulu", "Hilo", "Kailua", "Kaneohe", "Waipahu",
                   "Pearl City"),
        "New Hampshire": ("Manchester", "Nashua", "Concord", "Derry",
                          "Dover", "Rochester"),
        "Maine": ("Portland", "Lewiston", "Bangor", "South Portland",
                  "Auburn", "Biddeford"),
        "Montana": ("Billings", "Missoula", "Great Falls", "Bozeman",
                    "Butte", "Helena"),
        "Rhode Island": ("Providence", "Warwick", "Cranston", "Pawtucket",
                         "Fall River", "Newport"),
        "Delaware": ("Wilmington", "Dover", "Newark", "Middletown"),
        "South Dakota": ("Sioux Falls", "Rapid City", "Aberdeen", "Brookings"),
        "North Dakota": ("Fargo", "Bismarck", "Grand Forks", "Minot",
                         "West Fargo"),
        "Alaska": ("Anchorage", "Fairbanks", "Juneau", "Sitka", "Ketchikan"),
        "Vermont": ("Burlington", "South Burlington", "Rutland",
                    "Montpelier", "Barre"),
        "Wyoming": ("Cheyenne", "Casper", "Laramie", "Gillette", "Rock Springs"),
        "District of Columbia": ("Washington", "Arlington", "Bethesda", "Silver Spring"),
    },

    # ---------------- canada ----------------------------------------------
    "ca": {
        "Ontario": ("Toronto", "Ottawa", "Mississauga", "Hamilton", "London",
                    "Kitchener", "Windsor", "Oshawa", "Barrie", "Guelph",
                    "Sudbury", "Thunder Bay", "Peterborough", "Sarnia"),
        "Quebec": ("Montreal", "Quebec City", "Laval", "Gatineau", "Sherbrooke",
                   "Trois-Rivieres", "Saguenay", "Drummondville", "Saint-Jean-sur-Richelieu"),
        "British Columbia": ("Vancouver", "Surrey", "Victoria", "Burnaby",
                             "Richmond", "Kelowna", "Kamloops", "Nanaimo",
                             "Prince George", "Vernon"),
        "Alberta": ("Calgary", "Edmonton", "Red Deer", "Lethbridge",
                    "St. Albert", "Medicine Hat", "Grande Prairie", "Airdrie"),
        "Manitoba": ("Winnipeg", "Brandon", "Steinbach", "Thompson"),
        "Nova Scotia": ("Halifax", "Dartmouth", "Sydney", "Truro", "New Glasgow"),
        "New Brunswick": ("Moncton", "Saint John", "Fredericton", "Dieppe", "Bathurst"),
        "Saskatchewan": ("Saskatoon", "Regina", "Prince Albert", "Moose Jaw",
                         "Swift Current"),
        "Newfoundland and Labrador": ("St. John's", "Mount Pearl",
                                      "Corner Brook", "Gander"),
        "Prince Edward Island": ("Charlottetown", "Summerside", "Stratford"),
    },

    # ---------------- australia -------------------------------------------
    "au": {
        "New South Wales": ("Sydney", "Newcastle", "Wollongong", "Wagga Wagga",
                           "Albury", "Coffs Harbour", "Maitland", "Penrith",
                           "Tamworth", "Orange", "Dubbo"),
        "Victoria": ("Melbourne", "Geelong", "Ballarat", "Bendigo",
                     "Shepparton", "Mildura", "Frankston", "Warrnambool",
                     "Bairnsdale"),
        "Queensland": ("Brisbane", "Gold Coast", "Townsville", "Cairns",
                       "Toowoomba", "Mackay", "Rockhampton", "Hervey Bay",
                       "Sunshine Coast", "Maryborough"),
        "Western Australia": ("Perth", "Fremantle", "Mandurah", "Bunbury",
                              "Geraldton", "Kalgoorlie", "Albany", "Broome"),
        "South Australia": ("Adelaide", "Mount Gambier", "Whyalla",
                            "Port Lincoln", "Murray Bridge"),
        "Tasmania": ("Hobart", "Launceston", "Devonport", "Burnie", "Ulverstone"),
        "Northern Territory": ("Darwin", "Alice Springs", "Palmerston", "Nhulunbuy"),
        "ACT": ("Canberra",),
    },

    # ---------------- united kingdom -------------------------------------
    "gb": {
        "England": ("London", "Birmingham", "Manchester", "Leeds", "Liverpool",
                    "Sheffield", "Bristol", "Newcastle upon Tyne", "Nottingham",
                    "Leicester", "Coventry", "Bradford", "Southampton",
                    "Brighton", "Portsmouth", "Plymouth", "Reading", "Derby",
                    "Northampton", "Luton", "York", "Bath", "Oxford", "Cambridge"),
        "Scotland": ("Edinburgh", "Glasgow", "Aberdeen", "Dundee", "Inverness",
                     "Perth", "Stirling", "Paisley", "Ayr", "Falkirk"),
        "Wales": ("Cardiff", "Swansea", "Newport", "Wrexham", "Bangor",
                  "St Davids", "Wolverhampton"),
        "Northern Ireland": ("Belfast", "Derry", "Lisburn", "Newtownabbard",
                             "Bangor", "Armagh", "Craigavon"),
        "Greater London": ("Croydon", "Barnet", "Ealing", "Greenwich", "Hackney",
                           "Harrow", "Hounslow", "Islington", "Kingston",
                           "Lambeth", "Lewisham", "Newham", "Richmond",
                           "Southwark", "Sutton", "Tower Hamlets", "Wandsworth",
                           "Westminster", "Enfield", "Brent"),
    },

    # ---------------- ireland ---------------------------------------------
    "ie": {
        "Leinster": ("Dublin", "Dún Laoghaire", "Bray", "Navan", "Drogheda",
                     "Naas", "Newbridge", "Kildare", "Carlow", "Wexford",
                     "Kilkenny", "Dundalk", "Athlone", "Ashbourne"),
        "Munster": ("Cork", "Limerick", "Waterford", "Tralee", "Killarney",
                    "Clonmel", "Ennis", "Youghal"),
        "Connacht": ("Galway", "Sligo", "Castlebar", "Ballina", "Tuam",
                     "Westport", "Roscommon"),
        "Ulster": ("Letterkenny", "Donegal", "Cavan", "Monaghan",
                   "Ballybofey", "Carrickmacross", "Enniskillen", "Bundoran"),
    },

    # ---------------- portugal --------------------------------------------
    "pt": {
        "Lisboa": ("Lisbon", "Sintra", "Cascais", "Amadora", "Almada",
                   "Oeiras", "Loures", "Vila Franca de Xira", "Odivelas",
                   "Setúbal", "Sesimbra", "Torres Vedras", "Mafra"),
        "Porto": ("Porto", "Vila Nova de Gaia", "Matosinhos", "Maia",
                 "Vila do Conde", "Póvoa de Varzim", "Espinho", "Valongo",
                 "Guimarães", "Famalicão", "Felgueiras", "Amarante"),
        "Faro": ("Faro", "Albufeira", "Lagos", "Portimão", "Tavira", "Loulé",
                 "Olhão", "Quarteira", "Vila Real de Santo António", "Silves"),
        "Braga": ("Braga", "Guimarães", "Barcelos", "Vila Nova de Famalicão",
                  "Vizela", "Ponte de Lima", "Santo Tirso", "Fafe"),
        "Coimbra": ("Coimbra", "Figueira da Foz", "Cantanhede", "Ílhavo",
                    "Condeixa-a-Nova", "Mealhada", "Montemor-o-Velho",
                    "Oliveira do Hospital"),
    },

    # ---------------- spain -----------------------------------------------
    "es": {
        "Madrid": ("Madrid", "Alcalá de Henares", "Móstoles", "Getafe",
                   "Leganés", "Fuenlabrada", "Pozuelo de Alarcón", "Las Rozas",
                   "Torrejón de Ardoz", "Alcorcón", "Parla"),
        "Cataluña": ("Barcelona", "Badalona", "Hospitalet de Llobregat",
                     "Sabadell", "Terrassa", "Girona", "Lleida", "Tarragona",
                     "Manresa", "Reus", "Mataró", "Sant Cugat del Vallès"),
        "Andalucía": ("Seville", "Málaga", "Córdoba", "Granada", "Almería",
                      "Marbella", "Cádiz", "Jaén", "Jerez de la Frontera",
                      "Dos Hermanas", "Algeciras", "Écija"),
        "Valencia": ("Valencia", "Alicante", "Elche", "Castellón de la Plana",
                     "Torrevieja", "Gandía", "Sagunto", "Cullera"),
        "Galicia": ("A Coruña", "Vigo", "Santiago de Compostela", "Ourense",
                    "Lugo", "Pontevedra", "Sanxenxo"),
        "País Vasco": ("Bilbao", "Vitoria-Gasteiz", "San Sebastián", "Getxo",
                       "Barakaldo", "Irún", "Eibar"),
        "Aragón": ("Zaragoza", "Huesca", "Teruel", "Calatayud", "Jaca"),
    },

    # ---------------- france ----------------------------------------------
    "fr": {
        "Île-de-France": ("Paris", "Boulogne-Billancourt", "Saint-Denis",
                          "Argenteuil", "Montreuil", "Versailles", "Créteil",
                          "Nanterre", "Vitry-sur-Seine", "Ivry-sur-Seine"),
        "Occitanie": ("Toulouse", "Montpellier", "Nîmes", "Perpignan",
                       "Béziers", "Avignon", "Castres"),
        "Grand Est": ("Strasbourg", "Reims", "Metz", "Nancy", "Mulhouse",
                      "Colmar", "Troyes", "Metz"),
        "Nouvelle-Aquitaine": ("Bordeaux", "Limoges", "Poitiers", "Pau",
                               "La Rochelle", "Bayonne", "Angoulême", "Périgueux"),
        "Provence-Alpes-Côte d'Azur": ("Marseille", "Nice", "Toulon",
                                       "Aix-en-Provence", "Avignon", "Cannes",
                                       "Hyères"),
        "Hauts-de-France": ("Lille", "Amiens", "Roubaix", "Tourcoing",
                            "Dunkerque", "Calais", "Valenciennes", "Arras"),
        "Auvergne-Rhône-Alpes": ("Lyon", "Grenoble", "Saint-Étienne",
                                 "Clermont-Ferrand", "Annecy", "Valence",
                                 "Villeurbanne", "Chambéry"),
    },

    # ---------------- germany ---------------------------------------------
    "de": {
        "Bayern": ("Munich", "Nuremberg", "Augsburg", "Regensburg", "Würzburg",
                   "Ingolstadt", "Fürth", "Erlangen", "Bamberg", "Passau"),
        "Berlin": ("Berlin", "Potsdam"),
        "Nordrhein-Westfalen": ("Cologne", "Düsseldorf", "Dortmund", "Essen",
                                "Duisburg", "Bochum", "Bonn", "Münster",
                                "Wuppertal", "Bielefeld", "Mönchengladbach",
                                "Neuss", "Hagen"),
        "Baden-Württemberg": ("Stuttgart", "Mannheim", "Karlsruhe", "Freiburg",
                              "Heidelberg", "Ulm", "Heilbronn", "Pforzheim",
                              "Reutlingen"),
        "Niedersachsen": ("Hanover", "Braunschweig", "Osnabrück", "Oldenburg",
                          "Wolfsburg", "Salzgitter", "Göttingen"),
        "Hessen": ("Frankfurt", "Wiesbaden", "Kassel", "Darmstadt",
                   "Offenbach", "Fulda"),
        "Sachsen": ("Dresden", "Leipzig", "Chemnitz", "Zwickau", "Görlitz"),
        "Hamburg": ("Hamburg",),
        "Schleswig-Holstein": ("Kiel", "Lübeck", "Flensburg", "Neumünster",
                               "Norderstedt"),
    },

    # ---------------- italy ------------------------------------------------
    "it": {
        "Lombardia": ("Milan", "Brescia", "Bergamo", "Monza", "Como",
                      "Pavia", "Varese", "Sesto San Giovanni"),
        "Lazio": ("Rome", "Latina", "Civitavecchia", "Viterbo", "Frosinone",
                  "Guidonia Montecelio"),
        "Campania": ("Naples", "Salerno", "Caserta", "Benevento", "Avellino",
                     "Nocera Inferiore", "Sorrento"),
        "Sicilia": ("Palermo", "Catania", "Messina", "Syracuse", "Trapani",
                    "Agrigento", "Ragusa", "Marsala", "Gela"),
        "Veneto": ("Venice", "Verona", "Padua", "Vicenza", "Treviso",
                   "Mestre", "Padova"),
        "Piemonte": ("Turin", "Novara", "Alessandria", "Asti", "Cuneo",
                     "Biella"),
        "Toscana": ("Florence", "Pisa", "Siena", "Livorno", "Lucca",
                    "Arezzo", "Prato", "Viareggio"),
    },

    # ---------------- netherlands ------------------------------------------
    "nl": {
        "Noord-Holland": ("Amsterdam", "Haarlem", "Alkmaar", "Zaanstad",
                          "Amstelveen", "Hoofddorp", "Velsen", "Hilversum"),
        "Zuid-Holland": ("Rotterdam", "The Hague", "Leiden", "Delft",
                         "Gouda", "Dordrecht", "Zoetermeer", "Katwijk"),
        "Utrecht": ("Utrecht", "Amersfoort", "Veenendaal", "Nieuwegein", "Zeist"),
        "Gelderland": ("Arnhem", "Nijmegen", "Apeldoorn", "Ede", "Doetinchem"),
        "Overijssel": ("Zwolle", "Enschede", "Deventer", "Hengelo", "Almelo"),
        "Friesland": ("Leeuwarden", "Drachten", "Sneek", "Heerenveen"),
    },

    # ---------------- belgium / austria / switzerland ---------------------
    "be": {
        "Vlaanderen": ("Ghent", "Antwerp", "Bruges", "Leuven", "Mechelen",
                       "Kortrijk", "Hasselt", "Sint-Niklaas", "Ostend", "Turnhout"),
        "Wallonia": ("Liège", "Charleroi", "Namur", "Mons", "La Louvière",
                     "Mouscron", "Verviers", "Dinant", "Arlon"),
        "Brussels": ("Brussels", "Schaerbeek", "Anderlecht", "Ixelles", "Uccle"),
    },
    "at": {
        "Wien": ("Vienna",),
        "Salzburg": ("Salzburg", "Hallein", "Saalfelden"),
        "Tirol": ("Innsbruck", "Kufstein", "Wörgl"),
        "Steiermark": ("Graz", "Bruck an der Mur", "Leoben"),
        "Kärnten": ("Klagenfurt", "Villach", "Wolfsberg"),
    },
    "ch": {
        "Zürich": ("Zurich", "Winterthur", "Uster", "Wetzikon"),
        "Genève": ("Geneva", "Carouge", "Nyon", "Onex"),
        "Basel": ("Basel", "Binningen", "Liestal", "Allschwil"),
        "Bern": ("Bern", "Thun", "Biel", "Köniz", "Burgdorf"),
        "Vaud": ("Lausanne", "Montreux", "Yverdon", "Morges"),
    },

    # ---------------- brazil / mexico / argentina -------------------------
    "br": {
        "São Paulo": ("São Paulo", "Campinas", "Santos", "Guarulhos",
                      "Ribeirão Preto", "Sorocaba", "São José dos Campos",
                      "Osasco", "Jundiaí"),
        "Rio de Janeiro": ("Rio de Janeiro", "São Gonçalo", "Duque de Caxias",
                           "Niterói", "Nova Iguaçu", "Petrópolis", "Campos dos Goytacazes"),
        "Minas Gerais": ("Belo Horizonte", "Uberlândia", "Contagem",
                         "Juiz de Fora", "Betim", "Montes Claros"),
        "Bahia": ("Salvador", "Feira de Santana", "Vitória da Conquista",
                  "Ilhéus", "Juazeiro", "Camaçari"),
        "Paraná": ("Curitiba", "Londrina", "Maringá", "Ponta Grossa",
                   "Cascavel", "Foz do Iguaçu", "Toledo"),
        "Rio Grande do Sul": ("Porto Alegre", "Caxias do Sul", "Pelotas",
                              "Canoas", "Santa Maria", "Passo Fundo"),
        "Santa Catarina": ("Florianópolis", "Joinville", "Blumenau",
                           "Chapecó", "Criciúma", "Itajaí"),
        "Distrito Federal": ("Brasília", "Taguatinga", "Ceilândia", "Gama"),
        "Goiás": ("Goiânia", "Aparecida de Goiânia", "Anápolis", "Rio Verde"),
        "Pernambuco": ("Recife", "Jaboatão dos Guararapes", "Olinda",
                       "Caruaru", "Petrolina"),
    },
    "mx": {
        "Ciudad de México": ("Mexico City", "Ecatepec", "Nezahualcóyotl",
                             "Tlalnepantla", "Iztapalapa", "Cuautitlán",
                             "Tláhuac"),
        "Jalisco": ("Guadalajara", "Zapopan", "Tlaquepaque", "Tlajomulco",
                    "Puerto Vallarta", "Tepatitlán"),
        "Nuevo León": ("Monterrey", "San Nicolás de los Garza", "Guadalupe",
                       "Apodaca", "Santa Catarina"),
        "Puebla": ("Puebla", "San Andrés Cholula", "Tehuacán", "Atlixco"),
        "Yucatán": ("Mérida", "Valladolid", "Progreso", "Tizimín"),
        "Quintana Roo": ("Cancún", "Playa del Carmen", "Chetumal", "Cozumel"),
        "Baja California": ("Tijuana", "Mexicali", "Ensenada", "Rosarito"),
        "Veracruz": ("Veracruz", "Xalapa", "Córdoba", "Coatzacoalcos"),
        "Querétaro": ("Santiago de Querétaro", "El Marqués", "Corregidora", "San Juan del Río"),
    },
    "ar": {
        "Buenos Aires": ("Buenos Aires", "La Plata", "Mar del Plata",
                         "Bahía Blanca", "Tandil", "San Isidro", "Pilar"),
        "Córdoba": ("Córdoba", "Río Cuarto", "Villa María", "San Francisco"),
        "Santa Fe": ("Santa Fe", "Rosario", "Rafaela"),
        "Mendoza": ("Mendoza", "San Rafael", "Godoy Cruz"),
        "Tucumán": ("San Miguel de Tucumán", "Yerba Buena", "Concepción"),
    },

    # ---------------- poland / south africa / india / turkey -------------
    "pl": {
        "Mazowieckie": ("Warsaw", "Radom", "Płock", "Siedlce", "Pruszków",
                        "Wołomin", "Wyszków"),
        "Małopolskie": ("Kraków", "Tarnów", "Nowy Sącz", "Oświęcim", "Wieliczka"),
        "Śląskie": ("Katowice", "Gliwice", "Zabrze", "Bytom", "Sosnowiec",
                    "Tychy", "Częstochowa"),
        "Pomorskie": ("Gdańsk", "Gdynia", "Słupsk", "Tczew", "Wejherowo"),
        "Wielkopolskie": ("Poznań", "Kalisz", "Konin", "Piła", "Gniezno"),
        "Dolnośląskie": ("Wrocław", "Wałbrzych", "Legnica", "Jelenia Góra", "Lubin"),
    },
    "za": {
        "Gauteng": ("Johannesburg", "Pretoria", "Soweto", "Benoni",
                    "Boksburg", "Vereeniging", "Midrand", "Kempton Park"),
        "Western Cape": ("Cape Town", "Stellenbosch", "Paarl", "George",
                         "Worcester", "Mossel Bay"),
        "KwaZulu-Natal": ("Durban", "Pietermaritzburg", "Newcastle",
                          "Richards Bay", "Ladysmith"),
        "Eastern Cape": ("Port Elizabeth", "East London", "Mthatha", "Queenstown"),
        "Kleinmond": ("Kleinmond", "Hermanus", "Cape Town", "Stellenbosch"),
    },
    "in": {
        "Maharashtra": ("Mumbai", "Pune", "Nagpur", "Nashik", "Thane",
                        "Aurangabad", "Navi Mumbai"),
        "Karnataka": ("Bengaluru", "Mysuru", "Hubballi", "Mangaluru",
                      "Belagavi", "Davanagere"),
        "Delhi": ("Delhi", "New Delhi", "Dwarka", "Rohini"),
        "Telangana": ("Hyderabad", "Warangal", "Nizamabad", "Karimnagar"),
        "Tamil Nadu": ("Chennai", "Coimbatore", "Madurai", "Tiruchirappalli",
                       "Salem", "Tiruppur"),
        "Gujarat": ("Ahmedabad", "Surat", "Vadodara", "Rajkot", "Bhavnagar"),
        "Uttar Pradesh": ("Lucknow", "Kanpur", "Agra", "Varanasi",
                          "Prayagraj", "Noida", "Ghaziabad", "Meerut"),
        "West Bengal": ("Kolkata", "Howrah", "Durgapur", "Siliguri", "Asansol"),
        "Rajasthan": ("Jaipur", "Jodhpur", "Udaipur", "Kota", "Ajmer"),
        "Punjab": ("Ludhiana", "Amritsar", "Jalandhar", "Patiala", "Bathinda"),
        "Kerala": ("Kochi", "Thiruvananthapuram", "Kozhikode", "Thrissur"),
        "Madhya Pradesh": ("Indore", "Bhopal", "Jabalpur", "Gwalior", "Ujjain"),
        "Haryana": ("Gurugram", "Faridabad", "Panipat", "Ambala", "Karnal"),
    },
    "tr": {
        "İstanbul": ("Istanbul", "Esenyurt", "Bakırköy", "Kadıköy",
                     "Beşiktaş", "Üsküdar"),
        "Ankara": ("Ankara", "Keçiören", "Yenimahalle", "Çankaya"),
        "İzmir": ("Izmir", "Karşıyaka", "Bornova", "Çeşme", "Bergama"),
        "Antalya": ("Antalya", "Alanya", "Manavgat", "Kemer", "Kaş"),
    },
}


# --------------------------------------------------------------------------- #
# country -> cities  (offered when the region is unknown / not catalogued)
# --------------------------------------------------------------------------- #

_COUNTRY: Dict[str, Tuple[str, ...]] = {
    "us": ("New York City", "Los Angeles", "Chicago", "Houston", "Phoenix",
           "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose",
           "Austin", "Jacksonville", "Fort Worth", "Columbus", "Charlotte",
           "Indianapolis", "Seattle", "Denver", "Washington", "Boston",
           "Nashville", "Baltimore", "Milwaukee", "Portland", "Las Vegas",
           "Detroit", "Memphis", "Oklahoma City", "Louisville"),
    "ca": ("Toronto", "Montreal", "Vancouver", "Calgary", "Edmonton",
           "Ottawa", "Winnipeg", "Quebec City", "Hamilton", "Halifax"),
    "gb": ("London", "Birmingham", "Manchester", "Glasgow", "Liverpool",
           "Leeds", "Sheffield", "Edinburgh", "Bristol", "Newcastle upon Tyne",
           "Nottingham", "Leicester", "Bradford", "Brighton", "Plymouth",
           "Southampton", "Coventry", "Reading"),
    "ie": ("Dublin", "Cork", "Limerick", "Galway", "Waterford", "Drogheda",
           "Dundalk", "Swords", "Bray", "Navan", "Kilkenny", "Tralee",
           "Westport", "Carrick-on-Shannon", "Enniscorthy"),
    "au": ("Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide",
           "Gold Coast", "Canberra", "Newcastle", "Wollongong", "Hobart"),
    "nz": ("Auckland", "Wellington", "Christchurch", "Hamilton", "Tauranga",
           "Napier", "Dunedin", "Nelson", "Rotorua", "New Plymouth",
           "Whangarei", "Palmerston North", "Queenstown", "Invercargill"),
    "de": ("Berlin", "Hamburg", "Munich", "Cologne", "Frankfurt", "Stuttgart",
           "Düsseldorf", "Dortmund", "Essen", "Leipzig", "Bremen", "Dresden",
           "Hanover", "Nuremberg", "Duisburg", "Bochum", "Wuppertal",
           "Bielefeld", "Bonn", "Münster", "Karlsruhe", "Mannheim", "Augsburg",
           "Wiesbaden", "Freiburg", "Kiel", "Mainz", "Erfurt", "Magdeburg"),
    "fr": ("Paris", "Marseille", "Lyon", "Toulouse", "Nice", "Nantes",
           "Montpellier", "Strasbourg", "Bordeaux", "Lille", "Rennes", "Reims",
           "Saint-Étienne", "Toulon", "Le Havre", "Grenoble", "Dijon",
           "Angers", "Nîmes", "Villeurbanne", "Clermont-Ferrand", "Le Mans",
           "Aix-en-Provence", "Brest", "Tours", "Amiens", "Limoges", "Annecy",
           "Perpignan", "Besançon", "Metz", "Orléans", "Rouen", "Mulhouse",
           "Caen", "Nancy"),
    "es": ("Madrid", "Barcelona", "Valencia", "Seville", "Zaragoza", "Málaga",
           "Murcia", "Palma", "Las Palmas de Gran Canaria", "Bilbao",
           "Alicante", "Córdoba", "Valladolid", "Vigo", "Gijón", "Granada",
           "Elche", "Oviedo", "Badalona", "Cartagena"),
    "pt": ("Lisbon", "Porto", "Braga", "Coimbra", "Faro", "Setúbal", "Aveiro",
           "Funchal", "Évora", "Leiria", "Viseu", "Guimarães", "Matosinhos",
           "Amadora", "Almada", "Viana do Castelo", "Castelo Branco", "Santarém"),
    "it": ("Rome", "Milan", "Naples", "Turin", "Palermo", "Genoa", "Bologna",
           "Florence", "Bari", "Catania", "Venice", "Verona", "Messina",
           "Padua", "Trieste", "Brescia", "Parma", "Taranto", "Prato",
           "Modena", "Reggio Calabria", "Perugia", "Ravenna", "Livorno",
           "Cagliari", "Foggia", "Rimini", "Salerno", "Ferrara", "Latina",
           "Monza", "Siracusa", "Bergamo", "Trento", "Vicenza", "Bolzano",
           "Novara", "Piacenza", "Ancona", "Udine", "Lecce"),
    "nl": ("Amsterdam", "Rotterdam", "The Hague", "Utrecht", "Eindhoven",
           "Tilburg", "Groningen", "Almere", "Breda", "Nijmegen", "Enschede",
           "Haarlem", "Arnhem", "Amersfoort", "Alkmaar", "Maastricht",
           "Dordrecht", "Zoetermeer", "Zwolle", "Delft", "Leiden", "Hilversum"),
    "be": ("Brussels", "Antwerp", "Ghent", "Charleroi", "Liège", "Bruges",
           "Namur", "Leuven", "Mons", "Aalst", "Mechelen", "Kortrijk"),
    "lu": ("Luxembourg City", "Esch-sur-Alzette", "Differdange", "Dudelange",
           "Ettelbruck", "Diekirch", "Wiltz", "Vianden", "Echternach"),
    "ch": ("Zurich", "Geneva", "Basel", "Bern", "Lausanne", "Winterthur",
           "Lucerne", "St. Gallen", "Lugano", "Biel", "Fribourg", "Schaffhausen"),
    "at": ("Vienna", "Graz", "Linz", "Salzburg", "Innsbruck", "Klagenfurt",
           "Villach", "Wels", "Sankt Pölten", "Dornbirn", "Steyr", "Leoben"),
    "pl": ("Warsaw", "Kraków", "Łódź", "Wrocław", "Poznań", "Gdańsk",
           "Szczecin", "Lublin", "Bydgoszcz", "Białystok", "Gdynia",
           "Częstochowa", "Radom", "Tychy", "Olsztyn", "Rzeszów", "Opole"),
    "se": ("Stockholm", "Gothenburg", "Malmö", "Uppsala", "Västerås", "Örebro",
           "Linköping", "Helsingborg", "Jönköping", "Norrköping", "Lund",
           "Umeå", "Gävle", "Visby", "Karlstad"),
    "no": ("Oslo", "Bergen", "Trondheim", "Stavanger", "Drammen", "Fredrikstad",
           "Kristiansand", "Tromsø", "Sandnes", "Bodø", "Ålesund", "Haugesund"),
    "dk": ("Copenhagen", "Aarhus", "Odense", "Aalborg", "Esbjerg", "Randers",
           "Kolding", "Horsens", "Vejle", "Roskilde", "Herning", "Silkeborg"),
    "fi": ("Helsinki", "Espoo", "Tampere", "Vantaa", "Oulu", "Turku",
           "Jyväskylä", "Kuopio", "Lahti", "Vaasa", "Joensuu", "Lappeenranta"),
    "im": ("Douglas", "Ramsey", "Peel", "Castletown", "Port Erin",
           "Port St Mary", "Laxey"),
    "gr": ("Athens", "Thessaloniki", "Patra", "Heraklion", "Larissa", "Volos",
           "Ioannina", "Chania", "Kalamata", "Rhodes", "Kavala", "Corfu"),
    "cz": ("Prague", "Brno", "Ostrava", "Plzeň", "Liberec", "Olomouc",
           "Ústí nad Labem", "České Budějovice", "Hradec Králové", "Pardubice", "Zlín"),
    "ro": ("Bucharest", "Cluj-Napoca", "Timișoara", "Iași", "Constanța",
           "Craiova", "Brașov", "Galați", "Ploiești", "Oradea", "Arad",
           "Sibiu", "Bacău"),
    "hu": ("Budapest", "Debrecen", "Szeged", "Miskolc", "Pécs", "Győr",
           "Nyíregyháza", "Kecskemét", "Székesfehérvár", "Sopron"),
    "br": ("São Paulo", "Rio de Janeiro", "Brasília", "Salvador", "Fortaleza",
           "Belo Horizonte", "Manaus", "Curitiba", "Recife", "Porto Alegre",
           "Campinas", "Goiânia", "Belém", "Maceió", "Natal", "Teresina",
           "Campo Grande", "Joinville", "Cuiabá", "Feira de Santana"),
    "mx": ("Mexico City", "Guadalajara", "Monterrey", "Puebla", "Tijuana",
           "León", "Ciudad Juárez", "Zapopan", "Mérida", "Querétaro",
           "Morelia", "Hermosillo", "Chihuahua", "Toluca", "Aguascalientes",
           "Saltillo", "Veracruz", "Cancún", "Nuevo Laredo"),
    "ar": ("Buenos Aires", "Córdoba", "Rosario", "Mendoza", "La Plata",
           "San Miguel de Tucumán", "Salta", "Santa Fe", "San Juan",
           "Resistencia", "Neuquén", "Bahía Blanca"),
    "co": ("Bogotá", "Medellín", "Cali", "Barranquilla", "Cartagena",
           "Cúcuta", "Bucaramanga", "Pereira", "Santa Marta", "Ibagué",
           "Manizales", "Villavicencio"),
    "cl": ("Santiago", "Valparaíso", "Concepción", "Antofagasta", "Temuco",
           "La Serena", "Rancagua", "Talca", "Arica", "Iquique"),
    "pe": ("Lima", "Arequipa", "Cusco", "Trujillo", "Chiclayo", "Piura",
           "Iquitos", "Huancayo", "Tacna", "Ica"),
    "ae": ("Dubai", "Abu Dhabi", "Sharjah", "Al Ain", "Ajman", "Ras Al Khaimah",
           "Fujairah", "Umm Al Quwain"),
    "sa": ("Riyadh", "Jeddah", "Mecca", "Medina", "Dammam", "Taif", "Tabuk",
           "Buraydah", "Khamis Mushait", "Abha"),
    "qa": ("Doha", "Al Rayyan", "Al Wakrah", "Umm Salal", "Al Khor",
           "Al Shamal", "Al Shahaniya"),
    "kw": ("Kuwait City", "Hawalli", "Salmiya", "Jahra", "Farwaniya",
           "Fahaheel", "Mangaf", "Ahmadi"),
    "om": ("Muscat", "Salalah", "Sohar", "Nizwa", "Sur", "Ibri", "Buraimi"),
    "il": ("Jerusalem", "Tel Aviv", "Haifa", "Rishon LeZion", "Petah Tikva",
           "Ashdod", "Netanya", "Beer Sheva", "Holon", "Ramat Gan"),
    "tr": ("Istanbul", "Ankara", "Izmir", "Bursa", "Antalya", "Adana",
           "Konya", "Gaziantep", "Mersin", "Kayseri", "Eskişehir",
           "Diyarbakır", "Samsun", "Denizli", "Şanlıurfa", "Trabzon", "Erzurum"),
    "eg": ("Cairo", "Alexandria", "Giza", "Port Said", "Suez", "Luxor",
           "Aswan", "Mansoura", "Tanta", "Asyut", "Ismailia", "Fayoum",
           "Zagazig", "Damietta"),
    "ma": ("Casablanca", "Rabat", "Marrakech", "Fes", "Tangier", "Agadir",
           "Meknes", "Oujda", "Kenitra", "Tetouan", "Essaouira"),
    "tn": ("Tunis", "Sousse", "Sfax", "Bizerte", "Gabes", "Ariana",
           "Kairouan", "Monastir"),
    "za": ("Johannesburg", "Cape Town", "Durban", "Pretoria",
           "Port Elizabeth", "Bloemfontein", "East London", "Nelspruit",
           "Polokwane", "Kimberley", "Pietermaritzburg", "Rustenburg", "Soweto"),
    "ng": ("Lagos", "Abuja", "Port Harcourt", "Kano", "Ibadan", "Benin City",
           "Kaduna", "Enugu", "Jos", "Ilorin"),
    "ke": ("Nairobi", "Mombasa", "Kisumu", "Nakuru", "Eldoret", "Thika",
           "Malindi", "Nyeri"),
    "gh": ("Accra", "Kumasi", "Tamale", "Takoradi", "Cape Coast"),
    "tz": ("Dar es Salaam", "Arusha", "Mwanza", "Dodoma", "Zanzibar City",
           "Mbeya", "Morogoro"),
    "ug": ("Kampala", "Entebbe", "Jinja", "Mbarara", "Gulu", "Mbale", "Arua"),
    "in": ("Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Ahmedabad", "Chennai",
           "Kolkata", "Pune", "Jaipur", "Lucknow", "Kanpur", "Nagpur", "Indore",
           "Bhopal", "Surat", "Coimbatore", "Kochi", "Chandigarh"),
    "pk": ("Karachi", "Lahore", "Islamabad", "Faisalabad", "Rawalpindi",
           "Multan", "Peshawar", "Quetta", "Hyderabad"),
    "bd": ("Dhaka", "Chattogram", "Sylhet", "Khulna", "Rajshahi",
           "Chittagong", "Barisal", "Rangpur"),
    "lk": ("Colombo", "Kandy", "Galle", "Jaffna", "Negombo", "Matara",
           "Kurunegala"),
    "id": ("Jakarta", "Surabaya", "Bandung", "Medan", "Denpasar", "Semarang",
           "Makassar", "Palembang", "Bekasi", "Tangerang", "Yogyakarta",
           "Bogor", "Depok", "Malang"),
    "my": ("Kuala Lumpur", "George Town", "Ipoh", "Johor Bahru", "Melaka",
           "Kota Kinabalu", "Shah Alam", "Kuching", "Kuantan", "Seremban",
           "Miri", "Petaling Jaya"),
    "sg": ("Singapore", "Woodlands", "Jurong", "Tampines", "Bedok",
           "Sengkang", "Hougang", "Yishun", "Punggol", "Bukit Batok"),
    "th": ("Bangkok", "Chiang Mai", "Phuket", "Pattaya", "Chonburi",
           "Ayutthaya", "Nonthaburi", "Udon Thani", "Khon Kaen",
           "Surat Thani", "Krabi", "Hua Hin"),
    "vn": ("Hanoi", "Ho Chi Minh City", "Da Nang", "Hai Phong", "Can Tho",
           "Hai Duong", "Bien Hoa", "Nha Trang", "Vinh", "Da Lat"),
    "ph": ("Manila", "Quezon City", "Davao City", "Cebu City", "Makati",
           "Taguig", "Pasig", "Caloocan", "Zamboanga City", "Iloilo City",
           "Bacolod", "Cagayan de Oro"),
    "hk": ("Hong Kong", "Kowloon", "Tsuen Wan", "Sha Tin", "Tuen Mun",
           "Yuen Long", "Tai Po", "Fanling", "Sai Kung"),
    "tw": ("Taipei", "New Taipei City", "Taoyuan", "Taichung", "Tainan",
           "Kaohsiung", "Hsinchu", "Keelung", "Chiayi", "Changhua"),
    "jp": ("Tokyo", "Yokohama", "Osaka", "Nagoya", "Sapporo", "Fukuoka",
           "Kobe", "Kawasaki", "Kyoto", "Saitama", "Hiroshima", "Sendai",
           "Chiba", "Kitakyushu", "Sakai", "Shizuoka", "Kumamoto"),
    "kr": ("Seoul", "Busan", "Incheon", "Daegu", "Daejeon", "Gwangju",
           "Suwon", "Ulsan", "Changwon", "Seongnam", "Jeonju", "Anyang"),
    "ua": ("Kyiv", "Kharkiv", "Odesa", "Dnipro", "Lviv", "Zaporizhzhia",
           "Kryvyi Rih", "Mykolaiv", "Vinnytsia", "Kherson", "Poltava",
           "Chernihiv", "Lutsk"),
    "kz": ("Almaty", "Astana", "Shymkent", "Karaganda", "Aktobe", "Taraz",
           "Pavlodar", "Oskemen", "Semey", "Atyrau", "Kostanay"),
    "ru": ("Moscow", "Saint Petersburg", "Novosibirsk", "Yekaterinburg",
           "Kazan", "Nizhny Novgorod", "Chelyabinsk", "Samara", "Omsk",
           "Rostov-on-Don", "Ufa", "Krasnoyarsk", "Perm", "Voronezh",
           "Volgograd"),
}


# --------------------------------------------------------------------------- #
# lookups
# --------------------------------------------------------------------------- #

def norm(text: str) -> str:
    """Case/accent/punctuation-insensitive key ("São Paulo" == "sao paulo")."""
    t = unicodedata.normalize("NFKD", str(text or ""))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.lower().replace("&", " and ")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


def _unique(seq: Sequence[str]) -> Tuple[str, ...]:
    seen, out = set(), []
    for item in seq:
        k = norm(item)
        if k and k not in seen:
            seen.add(k)
            out.append(item)
    return tuple(out)


_TABLE: Dict[str, Dict[str, Tuple[str, ...]]] = {
    iso: {norm(region): _unique(cities) for region, cities in regions.items()}
    for iso, regions in _REGIONS.items()
}
_FALLBACK: Dict[str, Tuple[str, ...]] = {iso: _unique(cities) for iso, cities in _COUNTRY.items()}


def match_region(iso: str, region: str) -> Optional[str]:
    """Best (loosest) match for a region name inside a country's table."""
    key = norm(region)
    if not key:
        return None
    table = _TABLE.get(iso, {})
    if key in table:
        return key
    for candidate in table:                      # "new york" ~ "new york state"
        if candidate.startswith(key) or key.startswith(candidate):
            return candidate
    return None


def _pretty(iso: str, key: str) -> str:
    """Show a region the way countries.py spells it, when possible."""
    from . import countries as CO          # local import: countries has no deps
    country = CO.BY_ISO.get(iso)
    if country:
        for state in country.states:
            if norm(state) == key:
                return state
    return key.title()


def candidates(iso: str, region: str = "") -> List[Tuple[str, str]]:
    """
    Ready-made (city, region) pairs to offer.

    * known region   -> the cities of that region
    * unknown region -> every catalogued city in the country, tagged with its
                        region so the user can still orient themselves
                        (a city that belongs to two regions is listed once)
    """
    iso = (iso or "").lower()
    match = match_region(iso, region)
    if match:
        label = _pretty(iso, match)
        return [(city, label) for city in _TABLE[iso][match]]
    pairs: List[Tuple[str, str]] = []
    seen: set = set()
    for key, cities in _TABLE.get(iso, {}).items():
        label = _pretty(iso, key)
        for city in cities:
            k = norm(city)
            if k not in seen:
                seen.add(k)
                pairs.append((city, label))
    for city in _FALLBACK.get(iso, ()):
        if norm(city) not in seen:
            seen.add(norm(city))
            pairs.append((city, ""))
    return pairs


def region_of(iso: str, city: str) -> str:
    """Which region a city belongs to ("" when it is not catalogued)."""
    key = norm(city)
    for region, cities in _TABLE.get((iso or "").lower(), {}).items():
        if any(norm(c) == key for c in cities):
            return _pretty((iso or "").lower(), region)
    return ""


def is_city(iso: str, name: str) -> bool:
    """
    True when the "region" the user picked is really a city name.

    Plenty of entries in the region list are cities (Japan's states are cities,
    Norway's too, Singapore's are districts...) - catching them here is what lets
    the wizard offer "Tokyo" straight back as the city.
    """
    iso = (iso or "").lower()
    key = norm(name)
    if not key or match_region(iso, name):
        return False
    if region_of(iso, name):
        return True
    return any(norm(c) == key for c in _FALLBACK.get(iso, ()))


def count() -> int:
    """How many cities the wizard can offer."""
    total = sum(len(v) for v in _FALLBACK.values())
    for table in _TABLE.values():
        total += len(table)                       # regions are counted once
    return total