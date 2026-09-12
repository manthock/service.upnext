# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, unicode_literals

import xbmc
import xbmcgui

import utils


BUTTON_CONTROL_ID = 3012


class SkipIntroPopup(xbmcgui.WindowXMLDialog, object):
    """Small popup used to offer Skip Intro."""

    __slots__ = (
        'monitor',
        'start_time',
        'end_time',
    )

    def __init__(self, *args, **kwargs):
        self.monitor = kwargs.get('monitor')
        self.start_time = kwargs.get('start_time')
        self.end_time = kwargs.get('end_time')

        super(SkipIntroPopup, self).__init__(*args)

    @classmethod
    def log(cls, msg, level=utils.LOGDEBUG):
        utils.log(msg, name=cls.__name__, level=level)

    def onInit(self):
        try:
            self.setFocusId(BUTTON_CONTROL_ID)
        except RuntimeError:
            pass
			
    def onDeinit(self):
        if self.monitor:
            self.monitor._skip_intro_popup = None

    def onClick(self, control_id):
        if control_id != BUTTON_CONTROL_ID:
            return

        if self.monitor:
            self.monitor._skip_intro()
        else:
            self.close()

    def onAction(self, action):
        action_id = action.getId()

        if action_id in (
            xbmcgui.ACTION_NAV_BACK,
            xbmcgui.ACTION_STOP,
        ):
            self.close()
            return

        if action_id == xbmcgui.ACTION_SELECT_ITEM:
            if self.getFocusId() == BUTTON_CONTROL_ID:
                if self.monitor:
                    self.monitor._skip_intro()
                else:
                    self.close()
