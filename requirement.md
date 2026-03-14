
对于现有的一些项目，我现在是想解决这个问题。我需要驱动geminiagent在VPS服务器上面，但是呢，而是电脑方便，但手机不驱动起来不方便，所以手机上我会用会用telegram电报的界面和机器人对话  他们市面上有那种CC connect这个项目https://github.com/chenhg5/cc-connect，但是呢，我觉得他使用go写的写复杂了，它会同时兼容好多个平台，搞得很麻烦你知道吗？我准备就是你，而且他写的很庞大，功能很复杂。实际上，我根本就不想做那些额外的抽象层，我仅仅想一个平台telegram，然后一个agent只支持一个gemini agent  然后主要是去驱动gemini的headless无头模式 相当于是，是一直跑VPS上，跑了一个Python的一个中间件服务器。他接到了telegram的机器人，负责转发这个机器人的绘画，还有转发到gemini这个过程   相当于仅仅是只是为了包装它文档里面命令行gemini的接口而已，只不过把这个很好的包装第一个体现在体现在这个telegram的界面啊，对应的命令而已，加上一些基本的服务启动升级的命令  就是作为一个中间件应该有的服务这个基础命令而已 主要参考的文档就在后面 # Headless mode reference

Headless mode provides a programmatic interface to Gemini CLI, returning
structured text or JSON output without an interactive terminal UI.

## Technical reference

Headless mode is triggered when the CLI is run in a non-TTY environment or when
providing a query with the `-p` (or `--prompt`) flag.

### Output formats

You can specify the output format using the `--output-format` flag.

#### JSON output

Returns a single JSON object containing the response and usage statistics.

- **Schema:**
  - `response`: (string) The model's final answer.
  - `stats`: (object) Token usage and API latency metrics.
  - `error`: (object, optional) Error details if the request failed.

#### Streaming JSON output

Returns a stream of newline-delimited JSON (JSONL) events.

- **Event types:**
  - `init`: Session metadata (session ID, model).
  - `message`: User and assistant message chunks.
  - `tool_use`: Tool call requests with arguments.
  - `tool_result`: Output from executed tools.
  - `error`: Non-fatal warnings and system errors.
  - `result`: Final outcome with aggregated statistics and per-model token usage
    breakdowns.

## Exit codes

The CLI returns standard exit codes to indicate the result of the headless
execution:

- `0`: Success.
- `1`: General error or API failure.
- `42`: Input error (invalid prompt or arguments).
- `53`: Turn limit exceeded.

## Next steps

- Follow the [Automation tutorial](/docs/cli/tutorials/automation) for practical
  scripting examples.
- See the [CLI reference](/docs/cli/cli-reference) for all available flags.  # Gemini CLI cheatsheet

This page provides a reference for commonly used Gemini CLI commands, options,
and parameters.

## CLI commands

| Command                            | Description                        | Example                                                      |
| ---------------------------------- | ---------------------------------- | ------------------------------------------------------------ |
| `gemini`                           | Start interactive REPL             | `gemini`                                                     |
| `gemini -p "query"`                | Query non-interactively            | `gemini -p "summarize README.md"`                            |
| `gemini "query"`                   | Query and continue interactively   | `gemini "explain this project"`                              |
| `cat file \| gemini`               | Process piped content              | `cat logs.txt \| gemini`<br>`Get-Content logs.txt \| gemini` |
| `gemini -i "query"`                | Execute and continue interactively | `gemini -i "What is the purpose of this project?"`           |
| `gemini -r "latest"`               | Continue most recent session       | `gemini -r "latest"`                                         |
| `gemini -r "latest" "query"`       | Continue session with a new prompt | `gemini -r "latest" "Check for type errors"`                 |
| `gemini -r "<session-id>" "query"` | Resume session by ID               | `gemini -r "abc123" "Finish this PR"`                        |
| `gemini update`                    | Update to latest version           | `gemini update`                                              |
| `gemini extensions`                | Manage extensions                  | See [Extensions Management](#extensions-management)          |
| `gemini mcp`                       | Configure MCP servers              | See [MCP Server Management](#mcp-server-management)          |

### Positional arguments

| Argument | Type              | Description                                                                                                |
| -------- | ----------------- | ---------------------------------------------------------------------------------------------------------- |
| `query`  | string (variadic) | Positional prompt. Defaults to interactive mode in a TTY. Use `-p/--prompt` for non-interactive execution. |

## Interactive commands

These commands are available within the interactive REPL.

| Command              | Description                              |
| -------------------- | ---------------------------------------- |
| `/skills reload`     | Reload discovered skills from disk       |
| `/agents reload`     | Reload the agent registry                |
| `/commands reload`   | Reload custom slash commands             |
| `/memory reload`     | Reload context files (e.g., `GEMINI.md`) |
| `/mcp reload`        | Restart and reload MCP servers           |
| `/extensions reload` | Reload all active extensions             |
| `/help`              | Show help for all commands               |
| `/quit`              | Exit the interactive session             |

## CLI Options

| Option                           | Alias | Type    | Default   | Description                                                                                                                                                            |
| -------------------------------- | ----- | ------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--debug`                        | `-d`  | boolean | `false`   | Run in debug mode with verbose logging                                                                                                                                 |
| `--version`                      | `-v`  | -       | -         | Show CLI version number and exit                                                                                                                                       |
| `--help`                         | `-h`  | -       | -         | Show help information                                                                                                                                                  |
| `--model`                        | `-m`  | string  | `auto`    | Model to use. See [Model Selection](#model-selection) for available values.                                                                                            |
| `--prompt`                       | `-p`  | string  | -         | Prompt text. Appended to stdin input if provided. Forces non-interactive mode.                                                                                         |
| `--prompt-interactive`           | `-i`  | string  | -         | Execute prompt and continue in interactive mode                                                                                                                        |
| `--sandbox`                      | `-s`  | boolean | `false`   | Run in a sandboxed environment for safer execution                                                                                                                     |
| `--approval-mode`                | -     | string  | `default` | Approval mode for tool execution. Choices: `default`, `auto_edit`, `yolo`                                                                                              |
| `--yolo`                         | `-y`  | boolean | `false`   | **Deprecated.** Auto-approve all actions. Use `--approval-mode=yolo` instead.                                                                                          |
| `--experimental-acp`             | -     | boolean | -         | Start in ACP (Agent Code Pilot) mode. **Experimental feature.**                                                                                                        |
| `--experimental-zed-integration` | -     | boolean | -         | Run in Zed editor integration mode. **Experimental feature.**                                                                                                          |
| `--allowed-mcp-server-names`     | -     | array   | -         | Allowed MCP server names (comma-separated or multiple flags)                                                                                                           |
| `--allowed-tools`                | -     | array   | -         | **Deprecated.** Use the [Policy Engine](/docs/reference/policy-engine) instead. Tools that are allowed to run without confirmation (comma-separated or multiple flags) |
| `--extensions`                   | `-e`  | array   | -         | List of extensions to use. If not provided, all extensions are enabled (comma-separated or multiple flags)                                                             |
| `--list-extensions`              | `-l`  | boolean | -         | List all available extensions and exit                                                                                                                                 |
| `--resume`                       | `-r`  | string  | -         | Resume a previous session. Use `"latest"` for most recent or index number (e.g. `--resume 5`)                                                                          |
| `--list-sessions`                | -     | boolean | -         | List available sessions for the current project and exit                                                                                                               |
| `--delete-session`               | -     | string  | -         | Delete a session by index number (use `--list-sessions` to see available sessions)                                                                                     |
| `--include-directories`          | -     | array   | -         | Additional directories to include in the workspace (comma-separated or multiple flags)                                                                                 |
| `--screen-reader`                | -     | boolean | -         | Enable screen reader mode for accessibility                                                                                                                            |
| `--output-format`                | `-o`  | string  | `text`    | The format of the CLI output. Choices: `text`, `json`, `stream-json`                                                                                                   |

## Model selection

The `--model` (or `-m`) flag lets you specify which Gemini model to use. You can
use either model aliases (user-friendly names) or concrete model names.

### Model aliases

These are convenient shortcuts that map to specific models:

| Alias        | Resolves To                                | Description                                                                                                               |
| ------------ | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| `auto`       | `gemini-2.5-pro` or `gemini-3-pro-preview` | **Default.** Resolves to the preview model if preview features are enabled, otherwise resolves to the standard pro model. |
| `pro`        | `gemini-2.5-pro` or `gemini-3-pro-preview` | For complex reasoning tasks. Uses preview model if enabled.                                                               |
| `flash`      | `gemini-2.5-flash`                         | Fast, balanced model for most tasks.                                                                                      |
| `flash-lite` | `gemini-2.5-flash-lite`                    | Fastest model for simple tasks.                                                                                           |

## Extensions management

| Command                                            | Description                                  | Example                                                                        |
| -------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------ |
| `gemini extensions install <source>`               | Install extension from Git URL or local path | `gemini extensions install https://github.com/user/my-extension`               |
| `gemini extensions install <source> --ref <ref>`   | Install from specific branch/tag/commit      | `gemini extensions install https://github.com/user/my-extension --ref develop` |
| `gemini extensions install <source> --auto-update` | Install with auto-update enabled             | `gemini extensions install https://github.com/user/my-extension --auto-update` |
| `gemini extensions uninstall <name>`               | Uninstall one or more extensions             | `gemini extensions uninstall my-extension`                                     |
| `gemini extensions list`                           | List all installed extensions                | `gemini extensions list`                                                       |
| `gemini extensions update <name>`                  | Update a specific extension                  | `gemini extensions update my-extension`                                        |
| `gemini extensions update --all`                   | Update all extensions                        | `gemini extensions update --all`                                               |
| `gemini extensions enable <name>`                  | Enable an extension                          | `gemini extensions enable my-extension`                                        |
| `gemini extensions disable <name>`                 | Disable an extension                         | `gemini extensions disable my-extension`                                       |
| `gemini extensions link <path>`                    | Link local extension for development         | `gemini extensions link /path/to/extension`                                    |
| `gemini extensions new <path>`                     | Create new extension from template           | `gemini extensions new ./my-extension`                                         |
| `gemini extensions validate <path>`                | Validate extension structure                 | `gemini extensions validate ./my-extension`                                    |

See [Extensions Documentation](/docs/extensions) for more details.

## MCP server management

| Command                                                       | Description                     | Example                                                                                              |
| ------------------------------------------------------------- | ------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `gemini mcp add <name> <command>`                             | Add stdio-based MCP server      | `gemini mcp add github npx -y @modelcontextprotocol/server-github`                                   |
| `gemini mcp add <name> <url> --transport http`                | Add HTTP-based MCP server       | `gemini mcp add api-server http://localhost:3000 --transport http`                                   |
| `gemini mcp add <name> <command> --env KEY=value`             | Add with environment variables  | `gemini mcp add slack node server.js --env SLACK_TOKEN=xoxb-xxx`                                     |
| `gemini mcp add <name> <command> --scope user`                | Add with user scope             | `gemini mcp add db node db-server.js --scope user`                                                   |
| `gemini mcp add <name> <command> --include-tools tool1,tool2` | Add with specific tools         | `gemini mcp add github npx -y @modelcontextprotocol/server-github --include-tools list_repos,get_pr` |
| `gemini mcp remove <name>`                                    | Remove an MCP server            | `gemini mcp remove github`                                                                           |
| `gemini mcp list`                                             | List all configured MCP servers | `gemini mcp list`                                                                                    |

See [MCP Server Integration](/docs/tools/mcp-server) for more details.

## Skills management

| Command                          | Description                           | Example                                           |
| -------------------------------- | ------------------------------------- | ------------------------------------------------- |
| `gemini skills list`             | List all discovered agent skills      | `gemini skills list`                              |
| `gemini skills install <source>` | Install skill from Git, path, or file | `gemini skills install https://github.com/u/repo` |
| `gemini skills link <path>`      | Link local agent skills via symlink   | `gemini skills link /path/to/my-skills`           |
| `gemini skills uninstall <name>` | Uninstall an agent skill              | `gemini skills uninstall my-skill`                |
| `gemini skills enable <name>`    | Enable an agent skill                 | `gemini skills enable my-skill`                   |
| `gemini skills disable <name>`   | Disable an agent skill                | `gemini skills disable my-skill`                  |
| `gemini skills enable --all`     | Enable all skills                     | `gemini skills enable --all`                      |
| `gemini skills disable --all`    | Disable all skills                    | `gemini skills disable --all`                     |

See [Agent Skills Documentation](/docs/cli/skills) for more details. # Automate tasks with headless mode

Automate tasks with Gemini CLI. Learn how to use headless mode, pipe data into
Gemini CLI, automate workflows with shell scripts, and generate structured JSON
output for other applications.

## Prerequisites

- Gemini CLI installed and authenticated.
- Familiarity with shell scripting (Bash/Zsh).

## Why headless mode?

Headless mode runs Gemini CLI once and exits. It's perfect for:

- **CI/CD:** Analyzing pull requests automatically.
- **Batch processing:** Summarizing a large number of log files.
- **Tool building:** Creating your own "AI wrapper" scripts.

## How to use headless mode

Run Gemini CLI in headless mode by providing a prompt with the `-p` (or
`--prompt`) flag. This bypasses the interactive chat interface and prints the
response to standard output (stdout). Positional arguments without the flag
default to interactive mode, unless the input or output is piped or redirected.

Run a single command:

```bash
gemini -p "Write a poem about TypeScript"
```

## How to pipe input to Gemini CLI

Feed data into Gemini using the standard Unix pipe `|`. Gemini reads the
standard input (stdin) as context and answers your question using standard
output.

Pipe a file:

**macOS/Linux**

```bash
cat error.log | gemini -p "Explain why this failed"
```

**Windows (PowerShell)**

```powershell
Get-Content error.log | gemini -p "Explain why this failed"
```

Pipe a command:

```bash
git diff | gemini -p "Write a commit message for these changes"
```

## Use Gemini CLI output in scripts

Because Gemini prints to stdout, you can chain it with other tools or save the
results to a file.

### Scenario: Bulk documentation generator

You have a folder of Python scripts and want to generate a `README.md` for each
one.

1.  Save the following code as `generate_docs.sh` (or `generate_docs.ps1` for
    Windows):

    **macOS/Linux (`generate_docs.sh`)**

    ```bash
    #!/bin/bash

    # Loop through all Python files
    for file in *.py; do
      echo "Generating docs for $file..."

      # Ask Gemini CLI to generate the documentation and print it to stdout
      gemini -p "Generate a Markdown documentation summary for @$file. Print the
      result to standard output." > "${file%.py}.md"
    done
    ```

    **Windows PowerShell (`generate_docs.ps1`)**

    ```powershell
    # Loop through all Python files
    Get-ChildItem -Filter *.py | ForEach-Object {
      Write-Host "Generating docs for $($_.Name)..."

      $newName = $_.Name -replace '\.py$', '.md'
      # Ask Gemini CLI to generate the documentation and print it to stdout
      gemini -p "Generate a Markdown documentation summary for @$($_.Name). Print the result to standard output." | Out-File -FilePath $newName -Encoding utf8
    }
    ```

2.  Make the script executable and run it in your directory:

    **macOS/Linux**

    ```bash
    chmod +x generate_docs.sh
    ./generate_docs.sh
    ```

    **Windows (PowerShell)**

    ```powershell
    .\generate_docs.ps1
    ```

    This creates a corresponding Markdown file for every Python file in the
    folder.

## Extract structured JSON data

When writing a script, you often need structured data (JSON) to pass to tools
like `jq`. To get pure JSON data from the model, combine the
`--output-format json` flag with `jq` to parse the response field.

### Scenario: Extract and return structured data

1.  Save the following script as `generate_json.sh` (or `generate_json.ps1` for
    Windows):

    **macOS/Linux (`generate_json.sh`)**

    ```bash
    #!/bin/bash

    # Ensure we are in a project root
    if [ ! -f "package.json" ]; then
      echo "Error: package.json not found."
      exit 1
    fi

    # Extract data
    gemini --output-format json "Return a raw JSON object with keys 'version' and 'deps' from @package.json" | jq -r '.response' > data.json
    ```

    **Windows PowerShell (`generate_json.ps1`)**

    ```powershell
    # Ensure we are in a project root
    if (-not (Test-Path "package.json")) {
      Write-Error "Error: package.json not found."
      exit 1
    }

    # Extract data (requires jq installed, or you can use ConvertFrom-Json)
    $output = gemini --output-format json "Return a raw JSON object with keys 'version' and 'deps' from @package.json" | ConvertFrom-Json
    $output.response | Out-File -FilePath data.json -Encoding utf8
    ```

2.  Run the script:

    **macOS/Linux**

    ```bash
    chmod +x generate_json.sh
    ./generate_json.sh
    ```

    **Windows (PowerShell)**

    ```powershell
    .\generate_json.ps1
    ```

3.  Check `data.json`. The file should look like this:

    ```json
    {
      "version": "1.0.0",
      "deps": {
        "react": "^18.2.0"
      }
    }
    ```

## Build your own custom AI tools

Use headless mode to perform custom, automated AI tasks.

### Scenario: Create a "Smart Commit" alias

You can add a function to your shell configuration to create a `git commit`
wrapper that writes the message for you.

**macOS/Linux (Bash/Zsh)**

1.  Open your `.zshrc` file (or `.bashrc` if you use Bash) in your preferred
    text editor.

    ```bash
    nano ~/.zshrc
    ```

    **Note**: If you use VS Code, you can run `code ~/.zshrc`.

2.  Scroll to the very bottom of the file and paste this code:

    ```bash
    function gcommit() {
      # Get the diff of staged changes
      diff=$(git diff --staged)

      if [ -z "$diff" ]; then
        echo "No staged changes to commit."
        return 1
      fi

      # Ask Gemini to write the message
      echo "Generating commit message..."
      msg=$(echo "$diff" | gemini -p "Write a concise Conventional Commit message for this diff. Output ONLY the message.")

      # Commit with the generated message
      git commit -m "$msg"
    }
    ```

    Save your file and exit.

3.  Run this command to make the function available immediately:

    ```bash
    source ~/.zshrc
    ```

**Windows (PowerShell)**

1.  Open your PowerShell profile in your preferred text editor.

    ```powershell
    notepad $PROFILE
    ```

2.  Scroll to the very bottom of the file and paste this code:

    ```powershell
    function gcommit {
      # Get the diff of staged changes
      $diff = git diff --staged

      if (-not $diff) {
        Write-Host "No staged changes to commit."
        return
      }

      # Ask Gemini to write the message
      Write-Host "Generating commit message..."
      $msg = $diff | gemini -p "Write a concise Conventional Commit message for this diff. Output ONLY the message."

      # Commit with the generated message
      git commit -m "$msg"
    }
    ```

    Save your file and exit.你主要是生成agent的prompt，我会用uv 包有模板来发行，然后 命令行启动，要给出设计期待的所有 命令，然后 架构，markdown转义，为了obsidian markdown变成 telegram支持的显示，然后 要处理好 streamjson格式，用户配置用简单的toml文件去配置，然后测试要完善，主要是中间件，对Gemini cli的封装
还有一点，telegram的界面应该是可以输入一些/command的，这样更友好


3.  Run this command to make the function available immediately:

    ```powershell
    . $PROFILE
    ```

4.  Use your new command:

    ```bash
    gcommit
    ```

    Gemini CLI will analyze your staged changes and commit them with a generated
    message.

## Next steps

- Explore the [Headless mode reference](/docs/cli/headless) for full JSON
  schema details.
- Learn about [Shell commands](/docs/cli/tutorials/shell-commands) to let the agent run scripts
  instead of just writing them.相当于你需要给我生成一份完整的架构设计指南 我扔给agent去执行的，我会用python uv分发直接命令行安装 命令行启动  这个中间件服务，得选型用什么cli包封装和用什么技术栈解决，还有复杂的stream-json格式处理，主要是消息格式的显示需要很好的对应telegram的格式obsidianmarkdown 到telegram，你设定一份详细的架构实现指南
