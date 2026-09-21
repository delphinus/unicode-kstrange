CATEGORY ?= S
SLUG     ?= kstrange
PY       ?= python3
SCRIPTS  := PYTHONPATH=scripts $(PY)

.PHONY: all fetch glyphs wiktionary zi-tools uk-source l2docs html \
        index check check-links check-utn43 clean distclean

all: fetch glyphs wiktionary zi-tools uk-source l2docs html index

## 入力データ (Unihan ほか) を cache/ へ取得し、版とハッシュを記録する
fetch:
	$(SCRIPTS) scripts/fetch_inputs.py

## 対象の字の字形 SVG を GlyphWiki から docs/glyphs/ へ取得する
glyphs:
	$(SCRIPTS) scripts/fetch_glyphs.py --category $(CATEGORY)

## 英語版 Wiktionary に項目がある字を調べて cache/ に残す
wiktionary:
	$(SCRIPTS) scripts/fetch_wiktionary.py --category $(CATEGORY)

## zi.tools の字義と、その典拠になっている字書・論文を cache/ に残す
zi-tools:
	$(SCRIPTS) scripts/fetch_zi_tools.py --category $(CATEGORY)

## UK-source の提出文書から用例証拠を cache/ に、代表字形を docs/fonts/ に取り出す
uk-source:
	$(SCRIPTS) scripts/fetch_uk_source.py

## USourceData.txt が挙げる UTC 文書の題名と PDF の URL を cache/ に残す
l2docs:
	$(SCRIPTS) scripts/fetch_l2docs.py --category $(CATEGORY)

## docs/<slug>/index.html を組み立てる
html:
	$(SCRIPTS) scripts/build_html.py --category $(CATEGORY) --slug $(SLUG)

## コレクションの一覧 docs/index.html を組み立てる
index:
	$(SCRIPTS) scripts/build_index.py

check: check-links check-utn43

## 生成物のリンクを叩く (SAMPLE=n でホストごとに n 本だけ)
SAMPLE ?= 0
check-links:
	$(SCRIPTS) scripts/check_links.py $(if $(filter-out 0,$(SAMPLE)),--sample $(SAMPLE))

## UTN #43 の PDF の記述と Unihan を比べる (poppler が要る)
check-utn43:
	$(SCRIPTS) scripts/check_utn43.py

## 生成物を消す (取得済みの入力は残す)
clean:
	rm -f docs/index.html
	rm -rf docs/glyphs docs/fonts docs/kstrange docs/uk

## 取得済みの入力も消す
distclean: clean
	rm -rf cache
