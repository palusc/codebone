"""Speak real MCP stdio to the packaged bridge, including a tool round trip."""
import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    executable = sys.argv[1]
    async with stdio_client(StdioServerParameters(command=executable)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert 'cb' in {tool.name for tool in tools.tools}
            result = await session.call_tool('cb', {})
            assert result.content and not result.isError
            print('Packaged MCP initialized, listed tools and completed cb()')


if __name__ == '__main__':
    asyncio.run(asyncio.wait_for(main(), timeout=60))
