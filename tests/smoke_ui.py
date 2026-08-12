#!/usr/bin/env python3
"""Validação local, sem rede, do protótipo navegável SYNERGIA."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


ROOT = Path(__file__).resolve().parents[1]
OUT = Path("/tmp/synergia-ui-smoke")
PAGES = [
    "index.html",
    "consulta.html",
    "monitor.html",
    "pendencias.html",
    "detalhe-pendencia.html?id=P-0031",
    "relatorios.html",
    "visualizar-relatorio.html?id=REL-20260731-01",
    "configuracoes.html",
]
TV_PAGES = [
    "index.html",
    "consulta.html?wo=WO-10293",
    "monitor.html",
    "pendencias.html",
    "detalhe-pendencia.html?id=P-0031",
    "relatorios.html",
    "visualizar-relatorio.html?id=REL-20260731-01",
]
PLACEHOLDERS = re.compile(
    r"\[(?:gr[aá]fico|tabela|lista|alertas?|resumo).*?\]|lorem ipsum|would go here",
    re.IGNORECASE,
)


def file_url(page: str) -> str:
    path, *query = page.split("?", 1)
    url = (ROOT / path).as_uri()
    return f"{url}?{query[0]}" if query else url


def build_driver(width: int, height: int) -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--window-size={width},{height}")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(width, height)
    return driver


def collect_common_errors(driver: webdriver.Chrome, page: str) -> list[str]:
    errors: list[str] = []
    severe = [entry for entry in driver.get_log("browser") if entry["level"] == "SEVERE"]
    errors.extend(f"{page}: console: {entry['message']}" for entry in severe)
    broken = driver.execute_script(
        "return [...document.images].filter(i => !i.complete || i.naturalWidth === 0).map(i => i.src)"
    )
    errors.extend(f"{page}: imagem quebrada: {src}" for src in broken)
    text = driver.find_element("tag name", "body").text
    if PLACEHOLDERS.search(text):
        errors.append(f"{page}: conteúdo provisório ainda visível")
    overflow_x = driver.execute_script(
        "return Math.max(document.body.scrollWidth,document.documentElement.scrollWidth)-window.innerWidth"
    )
    if overflow_x > 2:
        errors.append(f"{page}: overflow horizontal de {overflow_x}px")
    unnamed = driver.execute_script(
        """
        return [...document.querySelectorAll('button,input,select,textarea')]
          .filter(el => {
            if (el.disabled || el.type === 'hidden') return false;
            const label = el.labels && el.labels.length;
            return !label && !el.getAttribute('aria-label') && !el.getAttribute('title')
              && !(el.tagName === 'BUTTON' && el.textContent.trim());
          }).map(el => `${el.tagName.toLowerCase()}#${el.id || '(sem id)'}`);
        """
    )
    errors.extend(f"{page}: controle sem nome acessível: {item}" for item in unnamed)
    return errors


def check_normal(width: int, height: int) -> list[str]:
    errors: list[str] = []
    driver = build_driver(width, height)
    try:
        for page in PAGES:
            driver.get(file_url(page))
            time.sleep(0.15)
            driver.execute_script("localStorage.setItem('synergia-tv','false'); setTVMode(false)")
            errors.extend(collect_common_errors(driver, page))
            stem = page.split("?", 1)[0].replace(".html", "")
            driver.save_screenshot(str(OUT / f"{stem}-{width}x{height}.png"))
    finally:
        driver.quit()
    return errors


def check_tv(width: int, height: int, theme: str = "dark") -> list[str]:
    errors: list[str] = []
    driver = build_driver(width, height)
    try:
        for page in TV_PAGES:
            driver.get(file_url(page))
            driver.execute_script(
                "setTheme(arguments[0]); localStorage.setItem('synergia-tv','true'); setTVMode(true)",
                theme,
            )
            time.sleep(0.15)
            panel_count = driver.execute_script("return document.querySelectorAll('.tv-panel').length")
            for index in range(panel_count):
                active = driver.execute_script(
                    """
                    showTVPanel(arguments[0]);
                    const panel=document.querySelector('.tv-panel.active');
                    if(!panel) return null;
                    const r=panel.getBoundingClientRect();
                    return {text:panel.innerText.trim(), top:r.top,left:r.left,right:r.right,bottom:r.bottom,
                            scrollHeight:panel.scrollHeight,clientHeight:panel.clientHeight,
                            scrollWidth:panel.scrollWidth,clientWidth:panel.clientWidth};
                    """,
                    index,
                )
                time.sleep(0.55)
                if not active or len(active["text"]) < 50:
                    errors.append(f"{page}: painel de TV {index + 1} ausente ou vazio")
                elif (
                    active["right"] > width + 2
                    or active["bottom"] > height + 2
                    or active["scrollHeight"] > active["clientHeight"] + 2
                    or active["scrollWidth"] > active["clientWidth"] + 2
                ):
                    errors.append(f"{page}: painel de TV {index + 1} excede a viewport: {active}")
                stem = page.split("?", 1)[0].replace(".html", "")
                driver.save_screenshot(
                    str(OUT / f"tv-{theme}-{stem}-p{index + 1}-{width}x{height}.png")
                )
            errors.extend(collect_common_errors(driver, f"TV:{page}"))
    finally:
        driver.quit()
    return errors


def check_interactions() -> list[str]:
    """Exercita os fluxos principais sem depender de serviços externos."""
    errors: list[str] = []
    driver = build_driver(1440, 900)

    def load(page: str) -> None:
        driver.get(file_url(page))
        time.sleep(0.25)
        driver.execute_script("localStorage.setItem('synergia-tv','false'); setTVMode(false)")

    def expect(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    try:
        load("index.html")
        driver.execute_script("localStorage.clear()")
        driver.refresh()
        time.sleep(0.25)
        dashboard = driver.execute_script(
            """
            document.getElementById('filter-search').value='WO-10294';
            applyFilters(false);
            return {count:dashboardCurrentView.workorders.length,
                    id:dashboardCurrentView.workorders[0]?.id};
            """
        )
        expect(
            dashboard == {"count": 1, "id": "WO-10294"},
            f"dashboard: filtro por Workorder não foi aplicado: {dashboard}",
        )
        driver.find_element("id", "btn-executar").click()
        expect(
            "active" in driver.find_element("id", "modal-confirm").get_attribute("class"),
            "dashboard: confirmação de execução não abriu",
        )
        driver.find_element("id", "modal-confirm-action").click()
        expect(
            driver.find_element("id", "btn-executar").get_attribute("aria-busy") == "true",
            "dashboard: execução sintética não iniciou após confirmação",
        )

        load("consulta.html?lot=4587")
        query_text = driver.find_element("id", "result-area").text
        expect(
            "WO-10293" in query_text and "4587" in query_text,
            "consulta: pesquisa por lote não retornou a Workorder esperada",
        )

        load("monitor.html")
        monitor = driver.execute_script(
            """
            const control=document.getElementById('filter-result');
            control.value='falha'; control.dispatchEvent(new Event('change',{bubbles:true}));
            return {count:document.getElementById('execution-count').textContent,
                    rows:document.getElementById('execution-tbody').innerText};
            """
        )
        expect(
            monitor["count"].startswith("1 resultado") and "Falha" in monitor["rows"],
            f"monitor: filtro de falhas inconsistente: {monitor}",
        )
        manual = driver.execute_script(
            """
            document.getElementById('execution-filters').reset();
            document.getElementById('execution-filters').dispatchEvent(
              new Event('submit',{bubbles:true,cancelable:true}));
            document.getElementById('new-execution').click();
            document.getElementById('manual-source').value='N-FP';
            document.getElementById('manual-form').dispatchEvent(
              new Event('submit',{bubbles:true,cancelable:true}));
            return {modal:document.getElementById('manual-modal').classList.contains('active'),
                    rows:document.getElementById('execution-tbody').innerText};
            """
        )
        expect(
            not manual["modal"] and "EX-SIM-" in manual["rows"],
            f"monitor: execução manual sintética não foi registrada: {manual}",
        )

        load("pendencias.html")
        pending = driver.execute_script(
            """
            const control=document.getElementById('filter-impact');
            control.value='critico'; control.dispatchEvent(new Event('change',{bubbles:true}));
            return {count:document.getElementById('pending-count').textContent,
                    rows:document.getElementById('pending-tbody').innerText};
            """
        )
        expect(
            pending["count"].startswith("2 resultado")
            and pending["rows"].count("Crítico") == 2,
            f"pendências: filtro crítico inconsistente: {pending}",
        )

        load("detalhe-pendencia.html?id=P-0031")
        note_saved = driver.execute_script(
            """
            document.getElementById('note-text').value='Validação local sintética';
            document.getElementById('note-form').dispatchEvent(
              new Event('submit',{bubbles:true,cancelable:true}));
            return document.getElementById('history-list').innerText.includes(
              'Observação registrada: Validação local sintética');
            """
        )
        expect(note_saved, "detalhe: observação sintética não entrou no histórico")

        load("relatorios.html")
        report = driver.execute_script(
            """
            document.getElementById('filter-status').value='erro';
            document.getElementById('apply-reports').click();
            return {count:document.getElementById('report-count').textContent,
                    rows:document.getElementById('reports-table').innerText};
            """
        )
        expect(
            report["count"].startswith("1 resultado") and "Erro" in report["rows"],
            f"relatórios: filtro de erro inconsistente: {report}",
        )

        load("visualizar-relatorio.html?id=REL-20260731-01")
        tab = driver.execute_script(
            """
            document.querySelector('[data-view="oqc"]').click();
            return {selected:document.querySelector('[data-view="oqc"]').getAttribute('aria-selected'),
                    hidden:document.getElementById('view-oqc').hidden,
                    rows:document.getElementById('report-oqc-body').children.length};
            """
        )
        expect(
            tab["selected"] == "true" and not tab["hidden"] and tab["rows"] > 0,
            f"visualização: aba OQC não alternou corretamente: {tab}",
        )

        load("configuracoes.html")
        settings = driver.execute_script(
            """
            const density=document.getElementById('setting-density');
            density.value='compact'; density.dispatchEvent(new Event('change',{bubbles:true}));
            const theme=document.getElementById('setting-theme');
            theme.value='auto'; theme.dispatchEvent(new Event('change',{bubbles:true}));
            return {density:document.documentElement.dataset.density,
                    stored:JSON.parse(localStorage.getItem('synergia-settings')),
                    theme:localStorage.getItem('synergia-theme')};
            """
        )
        expect(
            settings["density"] == "compact"
            and settings["stored"]["density"] == "compact"
            and settings["stored"]["theme"] == "auto"
            and settings["theme"] == "auto",
            f"configurações: preferências não foram persistidas: {settings}",
        )
    except Exception as exc:  # deixa o relatório final indicar o fluxo interrompido
        errors.append(f"fluxos funcionais: exceção: {exc}")
    finally:
        driver.quit()
    return errors


def check_mobile_navigation_themes() -> list[str]:
    """Confere marca e contraste da navegação/indicadores nos dois temas."""
    errors: list[str] = []
    driver = build_driver(390, 844)
    try:
        driver.get(file_url("index.html"))
        time.sleep(0.25)
        driver.execute_script("localStorage.setItem('synergia-tv','false'); setTVMode(false)")
        mobile_logo_rects = {}
        for theme, expected_logo in (
            ("light", "logo-horizontal.png"),
            ("dark", "logo-negativa-horizontal.png"),
        ):
            driver.execute_script(
                "setTheme(arguments[0]); document.getElementById('sidebar-toggle').click();",
                theme,
            )
            time.sleep(0.25)
            result = driver.execute_script(
                """
                const sidebar=document.getElementById('sidebar');
                const logo=sidebar.querySelector('.sidebar-logo img');
                const items=[...sidebar.querySelectorAll('.sidebar-item span')];
                const labels=[...sidebar.querySelectorAll('.sidebar-group-label')];
                const rgb=value => (value.match(/[0-9.]+/g)||[]).slice(0,3).map(Number);
                const luminance=value => {
                  const channels=rgb(value).map(channel => {
                    const c=channel/255;
                    return c<=.03928?c/12.92:Math.pow((c+.055)/1.055,2.4);
                  });
                  return .2126*channels[0]+.7152*channels[1]+.0722*channels[2];
                };
                const ratios=items.map(item => {
                  const itemBackground=getComputedStyle(item.parentElement).backgroundColor;
                  const background=itemBackground.endsWith(', 0)')
                    ? getComputedStyle(sidebar).backgroundColor : itemBackground;
                  const a=luminance(getComputedStyle(item).color), b=luminance(background);
                  return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
                });
                const rect=logo.getBoundingClientRect();
                return {open:sidebar.classList.contains('open'),src:logo.src,
                        logoLeft:rect.left,logoTop:rect.top,
                        logoWidth:rect.width,logoHeight:rect.height,naturalWidth:logo.naturalWidth,
                        itemCount:items.filter(item=>getComputedStyle(item).display!=='none').length,
                        labelCount:labels.filter(label=>getComputedStyle(label).display!=='none').length,
                        minimumContrast:Math.min(...ratios)};
                """,
            )
            if (
                not result["open"]
                or not result["src"].endswith(expected_logo)
                or result["logoWidth"] < 185
                or result["logoHeight"] < 50
                or result["naturalWidth"] < 700
                or result["itemCount"] < 6
                or result["labelCount"] < 4
                or result["minimumContrast"] < 4.5
            ):
                errors.append(f"sidebar móvel {theme}: marca ou contraste insuficiente: {result}")
            mobile_logo_rects[theme] = result
            driver.save_screenshot(str(OUT / f"sidebar-{theme}-390x844.png"))
            driver.execute_script("closeSidebar()")

        if any(
            abs(mobile_logo_rects["light"][key] - mobile_logo_rects["dark"][key]) > 1
            for key in ("logoLeft", "logoTop", "logoWidth", "logoHeight")
        ):
            errors.append(f"sidebar móvel: logos clara e escura desalinhadas: {mobile_logo_rects}")

        driver.set_window_size(1440, 900)
        driver.get(file_url("index.html"))
        time.sleep(0.25)
        driver.execute_script("localStorage.setItem('synergia-tv','false'); setTVMode(false)")
        desktop_logo_rects = {}
        for theme, expected_logo in (
            ("light", "logo-horizontal.png"),
            ("dark", "logo-negativa-horizontal.png"),
        ):
            driver.execute_script("setTheme(arguments[0])", theme)
            time.sleep(0.15)
            result = driver.execute_script(
                """
                const rgb=value => (value.match(/[0-9.]+/g)||[]).slice(0,3).map(Number);
                const luminance=value => {
                  const channels=rgb(value).map(channel => {
                    const c=channel/255;
                    return c<=.03928?c/12.92:Math.pow((c+.055)/1.055,2.4);
                  });
                  return .2126*channels[0]+.7152*channels[1]+.0722*channels[2];
                };
                const contrast=element => {
                  const style=getComputedStyle(element);
                  const a=luminance(style.color), b=luminance(style.backgroundColor);
                  return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
                };
                const logo=document.querySelector('.sidebar-logo img');
                const logoRect=logo.getBoundingClientRect();
                const sidebar=document.querySelector('.sidebar');
                const sidebarNav=document.querySelector('.sidebar-nav');
                const cards=[...document.querySelectorAll('.kpi-card')];
                return {src:logo.src,
                        logoLeft:logoRect.left,logoTop:logoRect.top,
                        logoWidth:logoRect.width,logoHeight:logoRect.height,
                        sidebarOverflow:getComputedStyle(sidebar).overflow,
                        sidebarNavOverscroll:getComputedStyle(sidebarNav).overscrollBehaviorY,
                        sidebarNavOverflow:sidebarNav.scrollHeight-sidebarNav.clientHeight,
                        bodyPaddingBottom:parseFloat(getComputedStyle(document.body).paddingBottom),
                        badgeContrast:Math.min(...[...document.querySelectorAll('.badge')].map(contrast)),
                        accentedCards:cards.filter(card =>
                          parseFloat(getComputedStyle(card).borderTopWidth)>=4).length,
                        cardCount:cards.length};
                """
            )
            if (
                not result["src"].endswith(expected_logo)
                or result["badgeContrast"] < 4.5
                or result["accentedCards"] != result["cardCount"]
            ):
                errors.append(f"dashboard {theme}: marca ou indicadores sem contraste: {result}")
            if (
                result["sidebarOverflow"] != "hidden"
                or result["sidebarNavOverscroll"] != "contain"
                or result["sidebarNavOverflow"] > 1
                or result["bodyPaddingBottom"] != 0
            ):
                errors.append(f"dashboard {theme}: rolagem lateral indevida: {result}")
            desktop_logo_rects[theme] = result
            driver.save_screenshot(str(OUT / f"dashboard-{theme}-1440x900.png"))

        if any(
            abs(desktop_logo_rects["light"][key] - desktop_logo_rects["dark"][key]) > 1
            for key in ("logoLeft", "logoTop", "logoWidth", "logoHeight")
        ):
            errors.append(f"desktop: logos clara e escura desalinhadas: {desktop_logo_rects}")

        driver.set_window_size(1200, 800)
        driver.get(file_url("index.html"))
        time.sleep(0.25)
        collapsed = driver.execute_script(
            """
            setTheme('dark');
            const logo=document.querySelector('.sidebar-logo');
            const pseudo=getComputedStyle(logo,'::before');
            return {image:pseudo.backgroundImage,width:pseudo.width,height:pseudo.height,
                    realLogoDisplay:getComputedStyle(logo.querySelector('img')).display};
            """
        )
        if (
            "simbolo-negativo.png" not in collapsed["image"]
            or collapsed["realLogoDisplay"] != "none"
            or not 39 <= float(collapsed["width"].replace("px", "")) <= 41
            or not 39 <= float(collapsed["height"].replace("px", "")) <= 41
        ):
            errors.append(f"logo colapsada no tema escuro incorreta: {collapsed}")
        driver.save_screenshot(str(OUT / "dashboard-dark-collapsed-1200x800.png"))
    finally:
        driver.quit()
    return errors


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    errors.extend(check_normal(1920, 1080))
    errors.extend(check_normal(390, 844))
    errors.extend(check_tv(1920, 1080))
    errors.extend(check_tv(1366, 768))
    errors.extend(check_tv(1280, 720))
    errors.extend(check_tv(1280, 720, "light"))
    errors.extend(check_tv(1024, 640))
    errors.extend(check_interactions())
    errors.extend(check_mobile_navigation_themes())
    if errors:
        print("FALHAS:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print(
        "OK: 16 páginas responsivas, 75 painéis TV, 8 fluxos funcionais e "
        "5 variantes de tema/contraste validadas. "
        f"Capturas em {OUT}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
