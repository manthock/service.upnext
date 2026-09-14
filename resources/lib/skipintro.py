# -*- coding: utf-8 -*-
# GNU General Public License v2.0
# See COPYING or https://www.gnu.org/licenses/gpl-2.0.txt

from __future__ import absolute_import, division, unicode_literals

import xbmc
import xbmcgui


SKIP_INTRO_CONTROL = 9000


class SkipIntroDialog(xbmcgui.WindowXMLDialog):
    """Dialog displayed while an IntroDB intro can be skipped."""

    def __init__(self, *args, **kwargs):
        self.player = kwargs.pop('player')
        self.state = kwargs.pop('state')
        super(SkipIntroDialog, self).__init__(*args, **kwargs)

    def onInit(self):
        try:
            self.setFocusId(SKIP_INTRO_CONTROL)
        except Exception:
            pass

    def onAction(self, action):
        if action.getId() in (
            xbmcgui.ACTION_NAV_BACK,
            xbmcgui.ACTION_PREVIOUS_MENU,
        ):
            self.close()
            return

        super(SkipIntroDialog, self).onAction(action)

    def onClick(self, control_id):
        if control_id != SKIP_INTRO_CONTROL:
            return

        target = self.state.skip_intro_target

        if target is None:
            self.close()
            return

        try:
            current_time = self.player.getTime()
        except RuntimeError:
            current_time = 0.0

        if current_time >= target:
            self.close()
            return

        try:
            self.player.seekTime(target)
            self.state.skip_intro_prompted = True
            self.close()
        except RuntimeError:
            self.close()

    def onDeinit(self):
        self.state.skip_intro_prompted = True