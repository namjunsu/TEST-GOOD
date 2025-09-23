#!/usr/bin/env python3
"""
WebSocket 실시간 통신 시스템
==============================
양방향 실시간 통신 및 푸시 알림
"""

import asyncio
import websockets
import json
import uuid
from typing import Dict, Set, Any, Optional
from datetime import datetime
import threading
from dataclasses import dataclass
from enum import Enum
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MessageType(Enum):
    """메시지 타입"""
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    QUERY = "query"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    HEARTBEAT = "heartbeat"
    BROADCAST = "broadcast"
    ERROR = "error"
    STATUS_UPDATE = "status_update"


@dataclass
class Client:
    """클라이언트 정보"""
    id: str
    websocket: websockets.WebSocketServerProtocol
    connected_at: datetime
    last_heartbeat: datetime
    metadata: Dict[str, Any]


class WebSocketServer:
    """WebSocket 서버"""

    def __init__(self, host='localhost', port=8765):
        self.host = host
        self.port = port
        self.clients: Dict[str, Client] = {}
        self.rooms: Dict[str, Set[str]] = {}
        self.message_handlers = {}
        self.running = False

        # 메시지 핸들러 등록
        self._register_handlers()

    def _register_handlers(self):
        """기본 핸들러 등록"""
        self.register_handler(MessageType.QUERY, self._handle_query)
        self.register_handler(MessageType.HEARTBEAT, self._handle_heartbeat)

    def register_handler(self, message_type: MessageType, handler):
        """메시지 핸들러 등록"""
        self.message_handlers[message_type] = handler

    async def start(self):
        """서버 시작"""
        self.running = True
        logger.info(f"🚀 WebSocket 서버 시작: ws://{self.host}:{self.port}")

        # 하트비트 체크 시작
        asyncio.create_task(self._heartbeat_checker())

        # 서버 실행
        async with websockets.serve(
            self.handle_client,
            self.host,
            self.port
        ):
            await asyncio.Future()  # 무한 대기

    async def handle_client(self, websocket, path):
        """클라이언트 처리"""
        client_id = str(uuid.uuid4())
        client = Client(
            id=client_id,
            websocket=websocket,
            connected_at=datetime.now(),
            last_heartbeat=datetime.now(),
            metadata={}
        )

        self.clients[client_id] = client
        logger.info(f"✅ 클라이언트 연결: {client_id}")

        # 연결 메시지 전송
        await self._send_message(client, {
            'type': MessageType.CONNECT.value,
            'client_id': client_id,
            'timestamp': datetime.now().isoformat()
        })

        try:
            async for message in websocket:
                await self._process_message(client, message)

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"연결 종료: {client_id}")

        finally:
            await self._disconnect_client(client_id)

    async def _process_message(self, client: Client, raw_message: str):
        """메시지 처리"""
        try:
            message = json.loads(raw_message)
            message_type = MessageType(message.get('type'))

            # 하트비트 갱신
            client.last_heartbeat = datetime.now()

            # 핸들러 실행
            handler = self.message_handlers.get(message_type)
            if handler:
                await handler(client, message)
            else:
                await self._send_error(client, f"Unknown message type: {message_type}")

        except json.JSONDecodeError:
            await self._send_error(client, "Invalid JSON")
        except ValueError as e:
            await self._send_error(client, str(e))
        except Exception as e:
            logger.error(f"메시지 처리 오류: {e}")
            await self._send_error(client, "Internal error")

    async def _handle_query(self, client: Client, message: Dict):
        """쿼리 처리"""
        query = message.get('query')
        if not query:
            await self._send_error(client, "Query is required")
            return

        # 쿼리 처리 시뮬레이션
        response = {
            'type': MessageType.RESPONSE.value,
            'query': query,
            'result': f"처리 결과: {query}",
            'timestamp': datetime.now().isoformat()
        }

        await self._send_message(client, response)

        # 다른 클라이언트에게 브로드캐스트
        await self.broadcast({
            'type': MessageType.STATUS_UPDATE.value,
            'message': f"클라이언트 {client.id[:8]}가 쿼리 실행: {query[:20]}..."
        }, exclude_client=client.id)

    async def _handle_heartbeat(self, client: Client, message: Dict):
        """하트비트 처리"""
        await self._send_message(client, {
            'type': MessageType.HEARTBEAT.value,
            'timestamp': datetime.now().isoformat()
        })

    async def broadcast(self, message: Dict, room: Optional[str] = None, exclude_client: Optional[str] = None):
        """브로드캐스트"""
        message['type'] = MessageType.BROADCAST.value

        if room:
            # 특정 룸에만
            client_ids = self.rooms.get(room, set())
        else:
            # 모든 클라이언트
            client_ids = set(self.clients.keys())

        # 제외할 클라이언트
        if exclude_client:
            client_ids.discard(exclude_client)

        # 메시지 전송
        tasks = []
        for client_id in client_ids:
            if client_id in self.clients:
                client = self.clients[client_id]
                tasks.append(self._send_message(client, message))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def send_notification(self, client_id: str, notification: Dict):
        """개별 알림 전송"""
        if client_id in self.clients:
            client = self.clients[client_id]
            message = {
                'type': MessageType.NOTIFICATION.value,
                'notification': notification,
                'timestamp': datetime.now().isoformat()
            }
            await self._send_message(client, message)

    async def _send_message(self, client: Client, message: Dict):
        """메시지 전송"""
        try:
            await client.websocket.send(json.dumps(message))
        except Exception as e:
            logger.error(f"메시지 전송 실패: {e}")
            await self._disconnect_client(client.id)

    async def _send_error(self, client: Client, error: str):
        """에러 전송"""
        await self._send_message(client, {
            'type': MessageType.ERROR.value,
            'error': error,
            'timestamp': datetime.now().isoformat()
        })

    async def _disconnect_client(self, client_id: str):
        """클라이언트 연결 해제"""
        if client_id in self.clients:
            client = self.clients[client_id]

            # 룸에서 제거
            for room_clients in self.rooms.values():
                room_clients.discard(client_id)

            # 클라이언트 제거
            del self.clients[client_id]

            # 연결 종료
            try:
                await client.websocket.close()
            except:
                pass

            logger.info(f"❌ 클라이언트 연결 해제: {client_id}")

    async def _heartbeat_checker(self):
        """하트비트 체커"""
        while self.running:
            current_time = datetime.now()
            disconnected = []

            for client_id, client in self.clients.items():
                # 30초 이상 하트비트 없으면 연결 해제
                time_diff = (current_time - client.last_heartbeat).total_seconds()
                if time_diff > 30:
                    disconnected.append(client_id)

            # 연결 해제
            for client_id in disconnected:
                await self._disconnect_client(client_id)

            await asyncio.sleep(10)

    def join_room(self, client_id: str, room: str):
        """룸 참여"""
        if room not in self.rooms:
            self.rooms[room] = set()
        self.rooms[room].add(client_id)
        logger.info(f"👥 {client_id} joined room: {room}")

    def leave_room(self, client_id: str, room: str):
        """룸 퇴장"""
        if room in self.rooms:
            self.rooms[room].discard(client_id)
            if not self.rooms[room]:
                del self.rooms[room]
        logger.info(f"🚪 {client_id} left room: {room}")


class WebSocketClient:
    """WebSocket 클라이언트"""

    def __init__(self, url='ws://localhost:8765'):
        self.url = url
        self.websocket = None
        self.client_id = None
        self.running = False

    async def connect(self):
        """서버 연결"""
        self.websocket = await websockets.connect(self.url)
        self.running = True

        # 연결 메시지 수신
        message = await self.websocket.recv()
        data = json.loads(message)
        self.client_id = data.get('client_id')

        logger.info(f"✅ 서버 연결 성공: {self.client_id}")

        # 수신 루프 시작
        asyncio.create_task(self._receive_loop())

        # 하트비트 시작
        asyncio.create_task(self._heartbeat_loop())

    async def _receive_loop(self):
        """메시지 수신 루프"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                await self._handle_message(data)
        except websockets.exceptions.ConnectionClosed:
            logger.info("서버 연결 종료")
            self.running = False

    async def _handle_message(self, message: Dict):
        """메시지 처리"""
        message_type = message.get('type')

        if message_type == MessageType.RESPONSE.value:
            logger.info(f"📨 응답: {message.get('result')}")
        elif message_type == MessageType.NOTIFICATION.value:
            logger.info(f"🔔 알림: {message.get('notification')}")
        elif message_type == MessageType.BROADCAST.value:
            logger.info(f"📢 브로드캐스트: {message.get('message')}")
        elif message_type == MessageType.ERROR.value:
            logger.error(f"❌ 에러: {message.get('error')}")

    async def _heartbeat_loop(self):
        """하트비트 전송"""
        while self.running:
            await self.send({
                'type': MessageType.HEARTBEAT.value
            })
            await asyncio.sleep(15)

    async def send(self, message: Dict):
        """메시지 전송"""
        if self.websocket:
            await self.websocket.send(json.dumps(message))

    async def query(self, query: str):
        """쿼리 전송"""
        await self.send({
            'type': MessageType.QUERY.value,
            'query': query
        })

    async def disconnect(self):
        """연결 종료"""
        self.running = False
        if self.websocket:
            await self.websocket.close()


# 서버 실행 함수
async def run_server():
    """서버 실행"""
    server = WebSocketServer()
    await server.start()


# 클라이언트 테스트 함수
async def test_client():
    """클라이언트 테스트"""
    client = WebSocketClient()
    await client.connect()

    # 쿼리 테스트
    await client.query("테스트 쿼리 1")
    await asyncio.sleep(1)
    await client.query("테스트 쿼리 2")

    # 대기
    await asyncio.sleep(5)

    # 연결 종료
    await client.disconnect()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'client':
        print("🔌 WebSocket 클라이언트 시작")
        asyncio.run(test_client())
    else:
        print("🚀 WebSocket 서버 시작")
        print("클라이언트 테스트: python websocket_realtime.py client")
        asyncio.run(run_server())