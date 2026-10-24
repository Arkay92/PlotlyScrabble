"""Optional actual-browser checks. Start app.py on port 8051 first."""
import json
from pathlib import Path
import random
import sys
import os

from playwright.sync_api import sync_playwright, expect

sys.path.append(str(Path(__file__).resolve().parents[1]))
from wordgame.rules import new_game


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge',headless=True)
        page = browser.new_page(viewport={'width':1440,'height':1100})
        errors = []
        page.on('pageerror',lambda error:errors.append(str(error)))
        url = os.environ.get('SCRABBLE_TEST_URL','http://127.0.0.1:8051')
        page.goto(url)
        expect(page.locator('#start')).to_be_disabled()
        expect(page.locator('#setup')).to_be_visible()
        page.get_by_text('UK English',exact=True).click()
        expect(page.locator('#start')).to_be_enabled()
        page.locator('#player-one').fill('Alice')
        page.locator('#player-two').fill('Bob')
        page.locator('#start').click()
        expect(page.locator('.board-cell')).to_have_count(225)
        expect(page.locator('.dictionary-badge')).to_contain_text('UK English')
        artifacts = Path(__file__).resolve().parents[1]/'artifacts'
        artifacts.mkdir(exist_ok=True)
        page.screenshot(path=str(artifacts/'game-desktop.png'),full_page=True)

        # Deterministic rack for testing gestures and scoring, not production dealing.
        state = new_game('en_US',('Alice','Bob'),random.Random(42))
        state['racks'][0]=list('CATERS?')
        page.evaluate('(state) => sessionStorage.setItem("session",JSON.stringify(state))',state)
        page.reload()
        expect(page.locator('.dictionary-badge')).to_contain_text('US English')

        def idle():
            expect(page.locator('#game-view')).to_have_attribute('data-busy','false')

        def drag(source, target):
            page.locator(source).scroll_into_view_if_needed()
            start = page.locator(source).bounding_box()
            end = page.locator(target).bounding_box()
            page.mouse.move(start['x']+start['width']/2,start['y']+start['height']/2)
            page.mouse.down()
            page.mouse.move(end['x']+end['width']/2,end['y']+end['height']/2,steps=12)
            page.mouse.up()

        drag('#rack-0','#cell-111')
        expect(page.locator('#cell-111')).to_contain_text('C')
        idle()
        page.locator('#rack-1').click()
        expect(page.locator('#rack-1')).to_have_attribute('aria-pressed','true')
        page.locator('#cell-112').click()
        expect(page.locator('#cell-112')).to_contain_text('A')
        idle()
        page.locator('#rack-2').focus()
        page.keyboard.press('Enter')
        expect(page.locator('#rack-2')).to_have_attribute('aria-pressed','true')
        page.locator('#cell-113').focus()
        page.keyboard.press('Enter')
        expect(page.locator('#preview')).to_contain_text('10 points')
        expect(page.locator('#play-word')).to_be_enabled()
        idle()
        drag('#cell-113','.rack')
        expect(page.locator('#cell-113 .letter-tile')).to_have_count(0)
        idle()
        drag('#rack-2','#cell-113')
        expect(page.locator('#preview')).to_contain_text('10 points')
        idle()
        page.locator('#play-word').click()
        expect(page.locator('.handoff')).to_contain_text('Pass the device to Bob')
        expect(page.locator('.rack-slot')).to_have_count(0)
        expect(page.locator('.history-list')).to_contain_text('CAT')
        expect(page.locator('.score').first).to_have_text('10')
        idle()
        page.get_by_role('button',name='Reveal my tiles').click()
        expect(page.locator('.rack-slot')).to_have_count(7)
        page.reload()
        expect(page.locator('#cell-111')).to_contain_text('C')
        expect(page.locator('.score').first).to_have_text('10')
        expect(page.locator('.dictionary-badge')).to_contain_text('US English')

        # Verify blank assignment and an invalid word remain drafts.
        state['racks'][0]=list('?ATERSX')
        page.evaluate('(state) => sessionStorage.setItem("session",JSON.stringify(state))',state)
        page.reload()
        page.locator('#blank-letter').select_option('Z')
        drag('#rack-0','#cell-112')
        expect(page.locator('#cell-112 .tile-letter')).to_have_text('Z')
        expect(page.locator('#cell-112 .tile-points')).to_have_text('0')
        idle()
        drag('#rack-6','#cell-113')
        expect(page.locator('#preview')).to_contain_text('ZX is not')
        expect(page.locator('#play-word')).to_be_disabled()
        idle()
        page.get_by_role('button',name='Recall tiles',exact=True).click()
        expect(page.locator('.draft')).to_have_count(0)
        idle()
        page.get_by_role('button',name='Exchange tiles',exact=True).click()
        expect(page.get_by_role('button',name='Cancel exchange',exact=True)).to_be_visible()
        page.locator('#rack-0').click()
        expect(page.locator('#rack-0')).to_have_attribute('aria-pressed','true')
        idle()
        page.get_by_role('button',name='Exchange 1 selected tiles',exact=True).click()
        expect(page.locator('.handoff')).to_contain_text('Pass the device to Bob')
        expect(page.locator('.history-list')).to_contain_text('Exchanged 1 tiles')
        idle()
        page.get_by_role('button',name='Reveal my tiles').click()
        expect(page.get_by_role('button',name='Pass turn',exact=True)).to_be_enabled()
        idle()
        page.get_by_role('button',name='Pass turn',exact=True).click()
        expect(page.locator('.history-list')).to_contain_text('Passed')
        expect(page.locator('.handoff')).to_contain_text('Pass the device to Alice')

        # Computer mode responds automatically and never asks to reveal its rack.
        idle()
        page.get_by_role('button',name='Back to home',exact=True).click()
        expect(page.locator('#setup')).to_be_visible()
        page.get_by_text('Player vs computer',exact=True).click()
        expect(page.locator('#second-player-field')).to_be_hidden()
        page.get_by_text('US English',exact=True).click()
        page.locator('#start').click()
        expect(page.get_by_text('VS COMPUTER',exact=True)).to_be_visible()
        idle()
        page.get_by_role('button',name='Pass turn',exact=True).click()
        expect(page.locator('#turn-count')).to_have_text('2 turns',timeout=15000)
        expect(page.locator('#feedback')).to_contain_text('Computer')
        expect(page.locator('.rack-slot')).to_have_count(7)
        expect(page.locator('.handoff')).to_have_count(0)
        idle()
        page.get_by_role('button',name='Exchange tiles',exact=True).click()
        expect(page.get_by_role('button',name='Cancel exchange',exact=True)).to_be_visible()
        page.locator('#rack-0').click()
        expect(page.locator('#rack-0')).to_have_attribute('aria-pressed','true')
        idle()
        page.get_by_role('button',name='Exchange 1 selected tiles',exact=True).click()
        expect(page.locator('#turn-count')).to_have_text('4 turns',timeout=15000)
        page.reload()
        expect(page.get_by_text('VS COMPUTER',exact=True)).to_be_visible()
        expect(page.locator('#turn-count')).to_have_text('4 turns')
        expect(page.locator('.handoff')).to_have_count(0)
        page.screenshot(path=str(artifacts/'computer-desktop.png'),full_page=True)

        # Real touch-pointer dragging on a narrow viewport.
        context = browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
        mobile = context.new_page()
        mobile.goto(url)
        expect(mobile.locator('#start')).to_be_disabled()
        mobile.screenshot(path=str(artifacts/'setup-mobile.png'),full_page=True)
        mobile.get_by_text('US English',exact=True).tap()
        expect(mobile.locator('#start')).to_be_enabled()
        mobile.locator('#start').tap()
        expect(mobile.locator('.board-cell')).to_have_count(225)
        rects = [mobile.locator(selector).bounding_box() for selector in ('#rack-0','#cell-112')]
        # Scroll the rack and board target into the same viewport before dispatch.
        mobile.evaluate('window.scrollTo(0,250)')
        rects = [mobile.locator(selector).bounding_box() for selector in ('#rack-0','#cell-112')]
        client = context.new_cdp_session(mobile)
        start,end = [{'x':r['x']+r['width']/2,'y':r['y']+r['height']/2} for r in rects]
        client.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[start]})
        client.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[end]})
        client.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
        expect(mobile.locator('#cell-112')).to_have_class('board-cell dw draft')
        assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth')
        mobile.screenshot(path=str(artifacts/'game-mobile.png'),full_page=True)
        assert not errors,errors
        browser.close()
        print('Browser checks passed: both modes, automatic NPC replies, exchange, required dictionary, click, drag, keyboard, recall, score, handoff, persistence, blanks and touch.')


if __name__=='__main__':
    main()
