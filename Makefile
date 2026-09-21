CATEGORY ?= S
PY       ?= python3
SCRIPTS  := PYTHONPATH=scripts $(PY)

.PHONY: all fetch glyphs html check check-links check-utn43 clean distclean

all: fetch glyphs wiktionary html

## 入力データ (Unihan ほか) を cache/ へ取得し、版とハッシュを記録する
fetch:
	$(SCRIPTS) scripts/fetch_inputs.py

## 対象の字の字形 SVG を GlyphWiki から docs/glyphs/ へ取得する
glyphs:
	$(SCRIPTS) scripts/fetch_glyphs.py --category $(CATEGORY)

## 英語版 Wiktionary に項目がある字を調べて cache/ に残す
wiktionary:
	$(SCRIPTS) scripts/fetch_wiktionary.py --category $(CATEGORY)

## docs/index.html を組み立てる
html:
	$(SCRIPTS) scripts/build_html.py --category $(CATEGORY)

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
	rm -rf docs/glyphs

## 取得済みの入力も消す
distclean: clean
	rm -rf cache
