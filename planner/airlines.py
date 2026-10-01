"""Fallback airline display-name -> IATA code map (Google's metadata list is incomplete)."""

NAME_TO_CODE = {
    "IndiGo": "6E", "Air India": "AI", "Air India Express": "IX", "Akasa Air": "QP", "SpiceJet": "SG",
    "Qatar Airways": "QR", "Emirates": "EK", "Etihad": "EY", "Singapore Airlines": "SQ", "Cathay Pacific": "CX",
    "Turkish Airlines": "TK", "Lufthansa": "LH", "Air France": "AF", "KLM": "KL", "British Airways": "BA",
    "American": "AA", "United": "UA", "Delta": "DL", "Ethiopian": "ET", "Saudia": "SV", "Kuwait Airways": "KU",
    "Oman Air": "WY", "Gulf Air": "GF", "Air Canada": "AC", "Japan Airlines": "JL", "ANA": "NH",
    "Korean Air": "KE", "Thai": "TG", "Malaysia Airlines": "MH", "SriLankan": "UL", "Finnair": "AY",
    "Swiss": "LX", "Austrian": "OS", "Brussels Airlines": "SN", "Virgin Atlantic": "VS", "Iberia": "IB",
    "Avianca": "AV", "Copa": "CM", "Aeromexico": "AM", "Volaris": "Y4", "VivaAerobus": "VB",
    "Spirit": "NK", "Frontier": "F9", "JetBlue": "B6", "Southwest": "WN", "Alaska": "AS", "Sun Country": "SY",
}


def resolve(name: str, code: str = "") -> str:
    return code or NAME_TO_CODE.get(name, "")
