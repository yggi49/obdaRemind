#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import collections
import curses
import datetime
import locale
import os.path
import textwrap
import subprocess
import sys


WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday',
            'Thursday', 'Friday', 'Saturday']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
          'July', 'August', 'September', 'October', 'November', 'December']
STATUS_TEXT = ('l/h:±1d, j/k:±1w, f/b:±1m, n/p:±1y, t:today, r:reload, '
               'x:redraw, q:quit, scroll info area with , (down) and . (up)')


def check_output(command):
    '''Run a command with arguments and return its output as a byte string.'''
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    output, unused_err = process.communicate()
    retcode = process.poll()
    if retcode:
        raise subprocess.CalledProcessError(retcode, command, output=output)
    return output


class TextBox(object):
    ALIGN_RIGHT = 'rjust'
    ALIGN_LEFT = 'ljust'
    ALIGN_CENTER = 'center'

    def __init__(self, scr, x=0, y=0, width=0, height=0, text='',
                 align=ALIGN_LEFT):
        self.scr = scr
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.text = text
        self.align = align
        self.wrapper = textwrap.TextWrapper(width=width)
        self.content_height = 0
        self.offset = 0

    def relocate(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.wrapper = textwrap.TextWrapper(width=width)
        self.render()

    def _addstr(self, pos_x, pos_y, text, highlight=False):
        style = curses.A_REVERSE if highlight else curses.A_NORMAL
        if sys.version_info < (3,):
            text = text.encode('utf-8')
        try:
            self.scr.addstr(pos_y, pos_x, text, style)
        except curses.error as e:
            if e.args[0] == 'addstr() returned ERR':
                self.scr.addstr(pos_y, pos_x, text[:-1])
            else:
                raise

    def clear(self, highlight=False):
        for i in range(self.height):
            self._addstr(self.x, self.y + i, ' ' * self.width, highlight)

    def render(self, highlight=False, offset=0):
        if self.height < 1 or self.width < 1:
            return
        self.clear(highlight)
        text = self.get_text()
        lines = []
        for para in text.split('\n'):
            lines.extend(self.wrapper.fill(para).split('\n'))
        if self.align != TextBox.ALIGN_LEFT:
            lines = [getattr(line, self.align)(self.width) for line in lines]
        self.content_height = len(lines)
        self.offset = max(0, min(offset, self.content_height - self.height))
        for i in range(min(self.content_height, self.height)):
            self._addstr(self.x, self.y + i,
                         lines[i + self.offset], highlight)

    def scroll(self, lines):
        self.render(offset=self.offset + lines)

    def scroll_down(self):
        self.scroll(1)

    def scroll_up(self):
        self.scroll(-1)

    def set_text(self, text, align=None):
        self.text = text
        if align:
            self.align = align
        self.render(offset=0)

    def get_text(self):
        return self.text


class DateBox(TextBox):
    def __init__(self, scr, date, x=0, y=0, width=0, height=0):
        TextBox.__init__(self, scr, x, y, width, height)
        self.date = date
        self.reminders = []

    def set_reminders(self, date, *reminders):
        self.date = date
        self.reminders = list(reminders)
        self.render()

    def get_reminders(self):
        return self.reminders

    def clear_reminders(self):
        self.reminders = []

    def get_text(self):
        text = [str(self.date.day)]
        if self.reminders:
            text[0] += ' ({0})'.format(len(self.reminders))
        text.extend(['•{0}'.format(r) for r in self.reminders])
        return '\n'.join(text)


class ObdaRemind(object):
    def __init__(self, scr):
        self.scr = scr
        self.today = datetime.date.today()
        self.selected = None
        self.boxes = {
            'header': TextBox(scr, align=TextBox.ALIGN_CENTER),
            'notes': TextBox(scr),
            'status': TextBox(scr, text=STATUS_TEXT),
            'weekdays': [TextBox(scr, text=w, align=TextBox.ALIGN_CENTER)
                         for w in WEEKDAYS],
            'weeknumbers': [TextBox(scr) for i in range(6)],
            'days': [DateBox(scr, self.today) for i in range(42)],
        }
        curses.curs_set(0)
        curses.use_default_colors()

    def redraw(self):
        # Calculate dimensions of date boxes, notes area, and status bar.
        scr_height, scr_width = self.scr.getmaxyx()
        datebox_width = (scr_width - 8) // 9
        datebox_height = (scr_height - 9) // 6
        notes_width = scr_width - (datebox_width + 1) * 7 - 2
        notes_height = scr_height
        notes_border = scr_width - notes_width - 1
        status_height = scr_height - 6 * (datebox_height + 1) - 4
        # Draw the grid.
        self.scr.clear()
        self.scr.vline(0, notes_border, curses.ACS_SBSB, scr_height)
        self.scr.hline(1, 0, curses.ACS_BSBS, notes_border)
        self.scr.vline(1, notes_border, curses.ACS_SBSS, 1)
        for i in range(7):
            self.scr.vline(1, i * (datebox_width + 1) + 1, curses.ACS_BSSS, 1)
            self.scr.vline(2, i * (datebox_width + 1) + 1, curses.ACS_SBSB, 1)
        for i in range(6):
            v_offset = i * (datebox_height + 1) + 3
            self.scr.hline(v_offset, 0, curses.ACS_BSBS, notes_border)
            self.scr.vline(v_offset, notes_border, curses.ACS_SBSS, 1)
            for j in range(7):
                h_offset = j * (datebox_width + 1) + 1
                self.scr.vline(v_offset + 1, h_offset, curses.ACS_SBSB,
                               datebox_height)
                self.scr.hline(v_offset, h_offset, curses.ACS_SSSS, 1)
        if status_height >= 0:
            v_offset = scr_height - 1 - status_height
            self.scr.hline(v_offset, 0, curses.ACS_BSBS, notes_border)
            for i in range(7):
                self.scr.hline(v_offset, i * (datebox_width + 1) + 1,
                               curses.ACS_SSBS, 1)
            self.scr.vline(v_offset, notes_border, curses.ACS_SBSS, 1)
        # Relocate the text boxes.
        self.boxes['header'].relocate(0, 0, notes_border, 1)
        self.boxes['notes'].relocate(notes_border + 1, 0,
                                     notes_width, notes_height)
        self.boxes['status'].relocate(0, scr_height - status_height,
                                      notes_border, status_height)
        for i, box in enumerate(self.boxes['weekdays']):
            box.relocate(i * (datebox_width + 1) + 2, 2, datebox_width, 1)
        for i, box in enumerate(self.boxes['weeknumbers']):
            box.relocate(0, i * (datebox_height + 1) + 4, 1, datebox_height)
        for i, box in enumerate(self.boxes['days']):
            box.relocate((i % 7) * (datebox_width + 1) + 2,
                         (i // 7) * (datebox_height + 1) + 4,
                         datebox_width, datebox_height)

    def set_date(self, new_date):
        # Get the first day of the month, and the first sunday on or before
        # that date.
        first_date = new_date.replace(day=1)
        first_weekday = datetime.date.weekday(first_date)
        first_sunday = first_date \
                       - datetime.timedelta(days=(first_weekday + 1) % 7)
        # Load a new month?
        if (not self.selected or
            new_date.month != self.selected.month or
            new_date.year != self.selected.year):
            # Update month name and week numbers.
            for i, box in enumerate(self.boxes['weeknumbers']):
                first_of_week = first_date + datetime.timedelta(weeks=i)
                box.set_text(str(first_of_week.isocalendar()[1]))
            self.boxes['header'].set_text('{month} {year}'.format(
                month=MONTHS[new_date.month - 1], year=new_date.year,
            ))
            # Load reminders and update date boxes.
            reminders = check_output([
                'remind', '-gaaad', '-p', '-s+6',
                os.path.expanduser('~/.reminders'),
                '1', MONTHS[new_date.month - 1][:3], str(new_date.year),
            ]).decode('utf-8')
            self.calendar = collections.defaultdict(list)
            for reminder in reminders.split('\n')[5:-2]:
                date, _, _, _, _, description = reminder.split(' ', 5)
                self.calendar[date].append(description)
            for i, box in enumerate(self.boxes['days']):
                date = first_sunday + datetime.timedelta(days=i)
                key = date.strftime('%Y/%m/%d')
                box.set_reminders(date, *self.calendar[key])
        # Remove highlighting.
        else:
            self.boxes['days'][(self.selected - first_sunday).days].render()
        # Update the notes box.
        notes = [new_date.strftime('%a, %b %d, %y')]
        selected_index = (new_date - first_sunday).days
        notes.extend([
            '•{0}'.format(r)
            for r in self.boxes['days'][selected_index].get_reminders()
        ])
        self.boxes['notes'].set_text('\n\n'.join(notes))
        # Set the newly selected date and highlight it.
        self.selected = new_date
        self.boxes['days'][selected_index].render(highlight=True)

    def jump_days(self, days):
        self.set_date(self.selected + datetime.timedelta(days))

    def jump_months(self, months):
        month = (self.selected.month + months - 1) % 12 + 1
        year = self.selected.year + (self.selected.month + months - 1) // 12
        try:
            new_date = self.selected.replace(month=month, year=year)
        # Erm, get the last day of the month instead.
        except ValueError:
            new_date = self.selected.replace(month=month+1, day=1, year=year)\
                       - datetime.timedelta(days=1)
        self.set_date(new_date)

    def jump_years(self, years):
        year = self.selected.year + years
        try:
            new_date = self.selected.replace(year=year)
        # Ooops, that was February 29, but there is none this year.
        except ValueError:
            new_date = self.selected.replace(day=28, year=year)
        self.set_date(new_date)

    def run(self):
        self.redraw()
        self.set_date(self.today)
        while True:
            try:
                key = self.scr.getch()
            except curses.error as e:
                if e.args[0] == 'no input':
                    key = ord('x')
                else:
                    raise
            self.today = datetime.date.today()
            if key == curses.KEY_RESIZE:
                key = ord('x')
            if key == ord('q'):
                break
            elif key == ord('t'):
                self.set_date(self.today)
            elif key == ord('x'):
                self.redraw()
                self.set_date(self.selected)
            elif key == ord('r'):
                date = self.selected
                self.selected = None
                self.set_date(date)
            elif key == ord('l'):
                self.jump_days(1)
            elif key == ord('h'):
                self.jump_days(-1)
            elif key == ord('j'):
                self.jump_days(7)
            elif key == ord('k'):
                self.jump_days(-7)
            elif key == ord('f'):
                self.jump_months(1)
            elif key == ord('b'):
                self.jump_months(-1)
            elif key == ord('n'):
                self.jump_years(1)
            elif key == ord('p'):
                self.jump_years(-1)
            elif key == ord(','):
                self.boxes['notes'].scroll_down()
            elif key == ord('.'):
                self.boxes['notes'].scroll_up()


if __name__ == '__main__':
    locale.setlocale(locale.LC_ALL,'')
    curses.wrapper(lambda stdscr: ObdaRemind(stdscr).run())
