# NSE V8.0 — Liquidity threshold relaxation (Marathi)

## बदल
- मागील 20 पूर्ण, वेगवेगळ्या trading sessions मधील average daily traded value ची मर्यादा ₹5 कोटींवरून **₹2 कोटी** केली.
- ₹2 कोटी किंवा अधिक असल्यास PASS; ₹2 कोटींपेक्षा कमी असल्यास liquidity filter मधून reject.
- 20 वैध sessions किंवा कोणत्याही session चा valid traded value नसेल तर `WAIT_FOR_DATA` कायम.
- हा फक्त liquidity threshold बदल आहे. RVOL > 1.5, Delivery Category A/B, Fundamental collection, technical/news gates आणि बाकी architecture बदललेले नाहीत.
- हा बदल eligible candidates वाढवू शकतो; परंतु कमी liquidity असलेल्या stocks मध्ये spread/slippage चा धोका अधिक असू शकतो. Backtest/paper-trading मध्ये नवे results तपासा.

## GitHub वर apply
ZIP मधील files त्यांच्या त्याच relative paths वर add/replace करा, commit/push करा आणि `NSE Data Test` workflow चालवा.
