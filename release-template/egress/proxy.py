"""Allowlisted HTTPS CONNECT only. Resolve once, reject nonpublic IPs, connect to that IP."""
import asyncio
import ipaddress
import os
import re
import socket

HOST = re.compile(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}')


def allowed_hosts(value):
    hosts = {part.strip().lower() for part in value.split(',') if part.strip()}
    if len(hosts) > 3 or any(not HOST.fullmatch(host) for host in hosts):
        raise ValueError('Configure at most three exact public DNS hostnames.')
    return hosts


def public_addresses(host):
    result = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(row[4][0] for row in result))
    if not addresses or any(not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast or ipaddress.ip_address(ip).is_reserved for ip in addresses):
        raise ValueError('Nonpublic destinations are blocked.')
    return addresses


async def pipe(reader, writer):
    total = 0
    while chunk := await asyncio.wait_for(reader.read(16384), 25):
        total += len(chunk)
        if total > 4 * 1024 * 1024:
            raise ValueError('Tunnel transfer limit reached.')
        writer.write(chunk)
        await writer.drain()


async def serve(reader, writer, hosts):
    upstream = None
    started = False
    try:
        header = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 5)
        if len(header) > 8192:
            raise ValueError('Headers too large.')
        first = header.split(b'\r\n', 1)[0].decode('ascii')
        match = re.fullmatch(r'CONNECT ([a-zA-Z0-9.-]+):443 HTTP/1\.[01]', first)
        if not match or match[1].lower() not in hosts:
            raise ValueError('Destination not allowed.')
        ips = await asyncio.wait_for(asyncio.to_thread(public_addresses, match[1].lower()), 5)
        # Numeric address is used directly. TLS hostname verification remains with httpx.
        remote, upstream = await asyncio.wait_for(asyncio.open_connection(ips[0], 443), 5)
        writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
        await writer.drain()
        started = True
        tasks = [asyncio.create_task(pipe(reader, upstream)), asyncio.create_task(pipe(remote, writer))]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=30)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        if not started:
            try:
                writer.write(b'HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n')
                await writer.drain()
            except Exception:
                pass
    finally:
        if upstream:
            upstream.close()
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def main():
    hosts = allowed_hosts(os.getenv('CONNECT_ALLOWED_HOSTS', ''))
    slots = asyncio.Semaphore(24)
    async def handle(reader, writer):
        if slots.locked():
            writer.close()
            return
        async with slots:
            await serve(reader, writer, hosts)
    server = await asyncio.start_server(handle, '0.0.0.0', 8888, limit=8192)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    asyncio.run(main())
