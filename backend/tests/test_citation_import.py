from asr_backend.citation_import import parse_csv, parse_ris

RIS_WITH_DOI = (
    "TY  - JOUR\n"
    "TI  - RIS Study\n"
    "AB  - An RIS abstract\n"
    "AU  - Doe, Jane\n"
    "PY  - 2019\n"
    "DB  - PubMed\n"
    "DO  - 10.1000/ris-study\n"
    "ER  - \n"
)

RIS_WITHOUT_DOI = (
    "TY  - JOUR\n"
    "TI  - RIS Study No DOI\n"
    "AU  - Doe, Jane\n"
    "PY  - 2019\n"
    "DB  - PubMed\n"
    "ER  - \n"
)

CSV_HEADER_WITH_DOI = "title,abstract,authors,year,source,doi\n"


def test_parse_ris_populates_doi_when_present():
    result = parse_ris(RIS_WITH_DOI)

    assert result.citations[0].doi == "10.1000/ris-study"


def test_parse_ris_doi_is_none_when_absent():
    result = parse_ris(RIS_WITHOUT_DOI)

    assert result.citations[0].doi is None


def test_parse_ris_source_is_a_one_element_list():
    result = parse_ris(RIS_WITH_DOI)

    assert result.citations[0].source == ["PubMed"]


def test_parse_ris_source_is_empty_list_when_absent():
    ris_without_source = (
        "TY  - JOUR\nTI  - No Source Study\nAU  - Doe, Jane\nPY  - 2019\nER  - \n"
    )

    result = parse_ris(ris_without_source)

    assert result.citations[0].source == []


def test_parse_csv_populates_doi_when_present():
    result = parse_csv(
        CSV_HEADER_WITH_DOI + "Study A,An abstract,Jane Doe,2020,PubMed,10.1000/csv-study\n"
    )

    assert result.citations[0].doi == "10.1000/csv-study"


def test_parse_csv_doi_is_none_when_absent():
    result = parse_csv(CSV_HEADER_WITH_DOI + "Study A,An abstract,Jane Doe,2020,PubMed,\n")

    assert result.citations[0].doi is None


def test_parse_csv_doi_is_none_when_column_missing():
    result = parse_csv("title,abstract,authors,year,source\nStudy A,An abstract,Jane Doe,2020,PubMed\n")

    assert result.citations[0].doi is None


def test_parse_csv_doi_header_match_is_case_insensitive():
    result = parse_csv(
        "title,abstract,authors,year,source,DOI\n"
        "Study A,An abstract,Jane Doe,2020,PubMed,10.1000/case-insensitive\n"
    )

    assert result.citations[0].doi == "10.1000/case-insensitive"


def test_parse_csv_source_is_a_one_element_list():
    result = parse_csv(CSV_HEADER_WITH_DOI + "Study A,An abstract,Jane Doe,2020,PubMed,\n")

    assert result.citations[0].source == ["PubMed"]


def test_parse_csv_source_is_empty_list_when_absent():
    result = parse_csv("title,abstract,authors,year\nStudy A,An abstract,Jane Doe,2020\n")

    assert result.citations[0].source == []
