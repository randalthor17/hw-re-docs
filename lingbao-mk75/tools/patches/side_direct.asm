; Side-light direct mode: the host sets the side-light LEDs, and the side-light renderer stays off while it does.
; Apply with: python3 tools/mk75asm.py patch fw/build/mk75.asm fw/patches/side_direct.asm fw/build/mk75-side.asm \
;             fw/build/mk75-side.bin <current dump>
;
; Slots: 14 x RGB. Slots 0-6 -> XRAM 0x328 + n*6, slots 7-13 -> 0x35E + (n-7)*6 (one entry per LED-matrix column: columns
; 0-6 and 9-15, the ones the stock renderer fills; the scan ISR at 0x6207 loads them into the PWM registers via F_a8c8).
; Hardware (verified 2026-10-30): left strip = slots 0-5 front to back, slot 6 has no LED, right strip = slots 7-13.
; Each channel is stored the way the stock renderer stores it: 16-bit big-endian c*4 + base, base = code 0x27D7 + channel
; (c = 0 is off, as in the stock clear at 0xA779). Stock caps c at 80; 255 is brighter and fine.
;
; USB:   SET 0x08 (the key frame) carries them too: payload bytes 378-419 = slots 0-13, byte 420 = 0x5A marks them present.
;        Every USB report costs about 67 ms (EP0 takes 8 bytes per 1 ms frame, and the firmware only accepts the full 520
;        bytes), so riding along in the key frame keeps Direct at one report per frame. Frames without the marker (stock
;        hosts) leave the side light alone; the handler clears the marker after use.
;        SET 0x07, index 0, 1 block, block 0, length 42: slots 0-13 on their own (one more 67 ms report).
; Radio: command 0x08 (direct, never acknowledged) with layer 3: payload = first slot, then up to 4 x R G B (length 13);
;        slots past 13 are dropped. Each package stands alone, so a frame is 4 packages (slots 0, 4, 8, 12).
; Both start direct mode like USB 0x08 does (flags 0x42/0x43, timeout 0xDAA = 0), so they end the same way: about 2 s after
; the last frame the slow loop clears 0x43, the gate sees it, drops SIDE_ACTIVE and the stock side light returns.
;
; Flag SIDE_ACTIVE = bit 0x48 (byte 0x29 bit 0): no stock code uses the bit or its byte; SP starts at 0x79, so IRAM 0x29 is
; not stack. It is clear after reset (IRAM is cleared at start-up; the Keil init table at 0x9FCF only sets XRAM).
; Runs only when a command arrives (and in the renderer gate as two bit tests), and never writes flash.

;@site 0x03a1 2
	jnc    L_03c9                          ; cmd 0x08 offsets >= 378: into the receive buffer like other cmds (stock: dropped)
;@site 0x044e 4
	ljmp   SET_NOPAUSE                     ; stock: xrl a,#0x08 / jz L_0473 (A = cmd from IRAM 0x18)
	nop
;@site 0x04a1 3
	ljmp   SIDE_CMD                        ; SET dispatch slot for cmd 0x07 (stock: bare RET at 0x05E9)
;@site 0x04a4 3
	ljmp   KEY_CMD                         ; SET dispatch slot for cmd 0x08 (stock: ljmp L_056e)
;@site 0x2615 3
	ljmp   RX_SIDE                         ; radio 0x08, layers other than 1 and 2 (stock: ljmp L_27bc), A = layer - 1
;@site 0x3f00 3
	ljmp   SIDE_GATE                       ; side-light renderer entry (stock: jnb 0x54,L_3f06)
;@code
	.org 0xef33
SIDE_ACTIVE = 0x48

; USB SET pre-check. Stock sets bit 0x2A (pause the LED scan at 0x6295, F_EED9 drives the LED lines off, timer 0x098E)
; for every cmd but 0x08 and 0x8x, because the others write flash. 0x07 writes no flash, so it skips the pause like 0x08;
; without this every frame blanked all LEDs for about 2 s (seen on hardware 2026-10-30).
SET_NOPAUSE:
	xrl    a,#0x08
	jz     SN_SKIP
	cjne   a,#0x0f,SN_CONT                 ; 0x07 ^ 0x08
SN_SKIP:
	ljmp   L_0473
SN_CONT:
	ljmp   0x0452

; Renderer gate. Skip the stock renderer while side direct holds the slots; release once direct mode has timed out.
SIDE_GATE:
	jnb    SIDE_ACTIVE,SG_STOCK
	jb     0x43,SG_SKIP
	clr    SIDE_ACTIVE
SG_STOCK:
	jb     0x54,SG_SKIP                    ; the replaced stock test: bit 0x54 set = renderer off
	ljmp   L_3f06
SG_SKIP:
	ret

; USB SET 0x07. Payload at XRAM 0x09B7 (the USB receive buffer for every cmd but 0x08).
SIDE_CMD:
	lcall  SIDE_START
	mov    r2,#0x09
	mov    r3,#0xb7
	mov    r6,#0
	mov    r0,#14
	ljmp   SIDE_COPY

; USB SET 0x08: the stock direct handler, then the side slots if the frame carries them. The receive buffer starts at
; XRAM 0x09B7, so payload byte 378 is at 0x0B31 and the marker (byte 420) at 0x0B5B.
KEY_CMD:
	lcall  L_056e
	mov    dptr,#0x0b5b
	movx   a,@dptr
	cjne   a,#0x5a,KC_OUT
	clr    a
	movx   @dptr,a
	lcall  SIDE_START
	mov    r2,#0x0b
	mov    r3,#0x31
	mov    r6,#0
	mov    r0,#14
	ljmp   SIDE_COPY
KC_OUT:
	ret

; Radio 0x08, layer 3. Packet at XRAM 0x00A3: payload at 0x00A9 = first slot, then the RGB triplets from 0x00AA.
RX_SIDE:
	cjne   a,#0x02,RS_OUT
	lcall  SIDE_START
	mov    dptr,#0x00a9
	movx   a,@dptr
	mov    r6,a
	mov    r2,#0x00
	mov    r3,#0xaa
	mov    r0,#4
	lcall  SIDE_COPY
RS_OUT:
	ljmp   L_27bc

SIDE_START:
	setb   0x42
	setb   0x43
	clr    a
	mov    dptr,#0x0daa
	movx   @dptr,a
	inc    dptr
	movx   @dptr,a
	setb   SIDE_ACTIVE
	ret

; Copy R0 slots of R G B from XRAM R2:R3 into the slot entries from slot R6 on, stopping at slot 14.
; R4:R5 destination, R7 channel, R1 scratch; stock handlers clobber R0-R7 too.
SIDE_COPY:
	cjne   r6,#14,SP_GO
SP_GO:
	jnc    SP_DONE                         ; slot >= 14
	mov    a,r6
	cjne   a,#7,SP_IDX
SP_IDX:
	jc     SP_LOW
	add    a,#2                            ; slots 7-13 are columns 9-15
SP_LOW:
	mov    0xf0,#6
	mul    ab
	add    a,#0x28
	mov    r5,a
	clr    a
	addc   a,#0x03
	mov    r4,a                            ; R4:R5 = 0x0328 + column*6
	mov    r7,#0
SP_CH:
	mov    0x83,r2
	mov    0x82,r3
	movx   a,@dptr
	inc    dptr
	mov    r2,0x83
	mov    r3,0x82
	mov    0xf0,#4
	mul    ab                              ; B:A = c*4
	mov    r1,a
	mov    a,r7
	mov    dptr,#0x27d7
	movc   a,@a+dptr                       ; channel base
	add    a,r1
	mov    r1,a
	clr    a
	addc   a,0xf0
	mov    0x83,r4
	mov    0x82,r5
	movx   @dptr,a                         ; high byte first, as the renderer stores it
	inc    dptr
	mov    a,r1
	movx   @dptr,a
	inc    dptr
	mov    r4,0x83
	mov    r5,0x82
	inc    r7
	cjne   r7,#3,SP_CH
	inc    r6
	djnz   r0,SIDE_COPY
SP_DONE:
	ret

; Version tag for hosts (read with USB GET 0x88 block 119: offset 0x11B): "MKSD", version. 1 = SET 0x07 only,
; 2 = side slots in the 0x08 key frame as well.
	.org 0xeff0
	.db    0x4d,0x4b,0x53,0x44,0x02
