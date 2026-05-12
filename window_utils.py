import PySimpleGUI as sg

_active_stack = []


def register_active(window):
    '''Register a window as the currently active parent. Sub-windows opened next will center on it.'''
    _active_stack.append(window)


def unregister_active(window):
    '''Remove a window from the active stack.'''
    try:
        _active_stack.remove(window)
    except ValueError:
        pass


def _center_on_active(child):
    if not _active_stack:
        return
    parent = _active_stack[-1]
    try:
        child.refresh()
        px, py = parent.current_location()
        pw, ph = parent.size
        cw, ch = child.size
        # Note: don't clamp to (0, 0). On multi-monitor setups, monitors to the left of
        # or above the primary display use negative virtual-desktop coordinates, and
        # clamping there would yank the child onto the primary monitor.
        x = px + (pw - cw) // 2
        y = py + (ph - ch) // 2
        child.move(x, y)
    except Exception as e:
        print(f'Could not center child window on parent: {e}')


def subwindow(*args, **kwargs):
    '''
    Drop-in replacement for sg.Window() for child popups. Centers the new window on the
    topmost active parent (instead of the primary monitor) and pushes it onto the stack so
    any of its own sub-windows will also center correctly. Caller must call
    unregister_active(window) before window.close().
    '''
    kwargs['finalize'] = True
    # Start invisible so the user doesn't see the window flash at the default location
    # before we move it.
    kwargs.setdefault('alpha_channel', 0)
    window = sg.Window(*args, **kwargs)
    _center_on_active(window)
    register_active(window)
    try:
        window.set_alpha(1.0)
    except Exception:
        pass
    return window


# Patch sg.Window so PySimpleGUI's built-in popup helpers (popup_ok, popup_get_text,
# popup_get_date, ...) also center on the active parent. Those helpers construct sg.Window
# internally and bypass subwindow(), so without this patch they'd appear on the primary
# monitor regardless of where the parent is.
_original_window_init = sg.Window.__init__

def _patched_window_init(self, *args, **kwargs):
    # Recenter on the active parent whenever one is registered. PySimpleGUI's popups
    # pass `location=(None, None)` and `relative_location=(None, None)` explicitly,
    # so a "did the caller specify a location?" check via kwargs is unreliable —
    # always recenter instead. (The main window is created before anything is
    # registered, so this is a no-op for it.)
    auto_center = bool(_active_stack)
    if auto_center:
        kwargs['finalize'] = True
        kwargs.setdefault('alpha_channel', 0)
    _original_window_init(self, *args, **kwargs)
    if auto_center:
        _center_on_active(self)
        try:
            self.set_alpha(1.0)
        except Exception:
            pass

sg.Window.__init__ = _patched_window_init
