"""Bounded original SSE investor-relations attachment transport, never economics."""
import base64
import hashlib
import io
import re
from datetime import date
from urllib.request import HTTPRedirectHandler, Request, build_opener
from pypdf import PdfReader

MAX_BYTES = 4 * 1024 * 1024


def source_location(request):
    identifier = request.get("announcement_id")
    if (request.get("source") != "SSEINFO"
            or not re.fullmatch(r"\d{6}\.SH", str(request.get("symbol")))
            or not isinstance(identifier, str)
            or not re.fullmatch(r"20\d{18,30}", identifier)):
        raise ValueError("SSEINFO_PUBLIC_ATTACHMENT_ID_OR_MARKET_INVALID")
    stamp = date(int(identifier[:4]), int(identifier[4:6]), int(identifier[6:8]))
    start, end = date.fromisoformat(request["start_date"]), date.fromisoformat(request["end_date"])
    if not start <= stamp <= end or (end - start).days > 31:
        raise ValueError("SSEINFO_ATTACHMENT_DATE_OUTSIDE_WINDOW")
    return ("https://sns.sseinfo.com/resources/images/upload/"
            + identifier[:6] + "/" + identifier + ".pdf", stamp.isoformat())


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("SSEINFO_ATTACHMENT_REDIRECT_REFUSED")


def fetch(request):
    url, stamp = source_location(request)
    try:
        query = Request(url, headers={"User-Agent": "PublicCompanyResearch/1.0",
                                     "Referer": "https://sns.sseinfo.com/"})
        with build_opener(NoRedirect()).open(query, timeout=20) as response:
            if response.status != 200:
                raise ValueError("SSEINFO_ATTACHMENT_HTTP_STATUS")
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("SSEINFO_ATTACHMENT_BYTE_LIMIT")
        if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-8192:]:
            raise ValueError("SSEINFO_ATTACHMENT_NOT_PDF")
        pdf = PdfReader(io.BytesIO(raw), strict=True)
        if not 1 <= len(pdf.pages) <= 30:
            raise ValueError("SSEINFO_ATTACHMENT_PAGE_LIMIT")
        cover = "".join(page.extract_text() or "" for page in pdf.pages[:2])
        if request["symbol"].split(".")[0] not in cover:
            raise ValueError("SSEINFO_ATTACHMENT_ISSUER_NOT_IN_COVER")
        row = dict(title="Exchange investor-relations attachment " + request["symbol"],
                   announcement_id=request["announcement_id"], announced_at=stamp,
                   source_url=url, source="SSEINFO_OFFICIAL_ATTACHMENT_PDF",
                   document_sha256=hashlib.sha256(raw).hexdigest(), byte_count=len(raw),
                   pdf_base64=base64.b64encode(raw).decode("ascii"), pdf_pages=len(pdf.pages),
                   verification_state="ORIGINAL_BYTES_CAPTURED_CONTENT_NOT_AUDITED")
        return [row], dict(required=1, fetched=1, source_used=row["source"],
                          announcement_id=request["announcement_id"])
    except Exception as error:
        return [], dict(required=1, fetched=0, source_used="SSEINFO", error_type=type(error).__name__,
                        gap_reason="SSEINFO_ORIGINAL_ATTACHMENT_FETCH_FAILED",
                        error=str(error)[:160])
