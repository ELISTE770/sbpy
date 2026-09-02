import * as vscode from 'vscode';
import { LanguageClient, LanguageClientOptions, ServerOptions } from 'vscode-languageclient/node';

let client: LanguageClient | undefined;

export function activate(context: vscode.ExtensionContext) {
    const config = vscode.workspace.getConfiguration('sbpy');
    const serverPath = config.get<string>('serverPath', 'sbpy');

    const serverOptions: ServerOptions = {
        command: serverPath,
        args: ['lsp'],
        options: { shell: true }
    };

    const clientOptions: LanguageClientOptions = {
        documentSelector: [{ scheme: 'file', language: 'python' }],
        synchronize: {
            fileEvents: vscode.workspace.createFileSystemWatcher('**/*.py')
        }
    };

    client = new LanguageClient('sbpyLsp', 'SBpy Language Server', serverOptions, clientOptions);
    client.start();

    context.subscriptions.push(
        vscode.commands.registerCommand('sbpy.dashboard', () => {
            vscode.env.openExternal(vscode.Uri.parse('http://127.0.0.1:8080'));
        })
    );
}

export function deactivate(): Thenable<void> | undefined {
    return client ? client.stop() : undefined;
}
