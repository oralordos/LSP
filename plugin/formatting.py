from .core.logging import printf
from .core.protocol import Request
from .core.registry import client_for_view, LspTextCommand, session_for_view
from .core.types import ViewLike
from .core.url import filename_to_uri
from .core.views import region_to_range
import sublime_plugin
import threading

try:
    from typing import Dict, Any
    assert Dict and Any
except ImportError:
    pass


def options_for_view(view: ViewLike) -> 'Dict[str, Any]':
    return {
        "tabSize": view.settings().get("tab_size", 4),
        "insertSpaces": True
    }


class FormatOnSave(sublime_plugin.ViewEventListener):
    def has_client_with_capability(self, capability):
        session = session_for_view(self.view)
        if session and session.has_capability(capability):
            return True
        return False

    def on_pre_save(self):
        if self.has_client_with_capability('documentFormattingProvider'):
            client = client_for_view(self.view)
            if client:
                cv = threading.Condition()
                params = {
                    "textDocument": {
                        "uri": filename_to_uri(self.view.file_name())
                    },
                    "options": options_for_view(self.view)
                }
                returnData = {}
                request = Request.formatting(params)
                with cv:
                    client.send_request(
                        request, lambda response: self.handle_save_response(response, cv, returnData))
                    if cv.wait(5):
                        self.view.run_command('lsp_apply_document_edit', {'changes': returnData['response']})
                    else:
                        printf('Timeout while formatting before saving')

    @staticmethod
    def handle_save_response(response, cv, returnData):
        with cv:
            returnData['response'] = response
            cv.notify()


class LspFormatDocumentCommand(LspTextCommand):
    def __init__(self, view):
        super().__init__(view)

    def is_enabled(self, event=None):
        return self.has_client_with_capability('documentFormattingProvider')

    def run(self, edit):
        client = client_for_view(self.view)
        if client:
            pos = self.view.sel()[0].begin()
            params = {
                "textDocument": {
                    "uri": filename_to_uri(self.view.file_name())
                },
                "options": options_for_view(self.view)
            }
            request = Request.formatting(params)
            client.send_request(
                request, lambda response: self.handle_response(response, pos))

    def handle_response(self, response, pos):
        self.view.run_command('lsp_apply_document_edit',
                              {'changes': response})


class LspFormatDocumentRangeCommand(LspTextCommand):
    def __init__(self, view):
        super().__init__(view)

    def is_enabled(self, event=None):
        if self.has_client_with_capability('documentRangeFormattingProvider'):
            if len(self.view.sel()) == 1:
                region = self.view.sel()[0]
                if region.begin() != region.end():
                    return True
        return False

    def run(self, _):
        client = client_for_view(self.view)
        if client:
            region = self.view.sel()[0]
            params = {
                "textDocument": {
                    "uri": filename_to_uri(self.view.file_name())
                },
                "range": region_to_range(self.view, region).to_lsp(),
                "options": options_for_view(self.view)
            }
            client.send_request(Request.rangeFormatting(params),
                                lambda response: self.view.run_command('lsp_apply_document_edit',
                                                                       {'changes': response}))
