// SPDX-License-Identifier: MIT
// Bounded PawnIO adapter for the Linux Acer A515-54G PMC3 protocol.
// Requires official signing before it can be used with the signed PawnIO edition.
// No arbitrary port/register access is exposed. Callers must additionally validate DMI.
#include <pawnio.inc>

new bool:g_ready = false;
new bool:g_changed = false;
new g_original;

reg_read(index) {
    io_out_byte(0x2e, index);
    return io_in_byte(0x2f);
}
reg_write(index, value) {
    io_out_byte(0x2e, index);
    io_out_byte(0x2f, value);
}
select_sub(sub) {
    reg_write(0x2e, sub);
    io_out_byte(0x2e, 0x2f);
}
memory_read(address) {
    select_sub(0x11); io_out_byte(0x2f, address >> 8);
    select_sub(0x10); io_out_byte(0x2f, address & 255);
    select_sub(0x12); return io_in_byte(0x2f);
}
NTSTATUS:sample(out[3]) {
    new index = io_in_byte(0x2e);
    io_out_byte(0x2e, 0x2e);
    new sub = io_in_byte(0x2f);
    select_sub(0x11); new hi = io_in_byte(0x2f);
    select_sub(0x10); new lo = io_in_byte(0x2f);
    new NTSTATUS:result = STATUS_SUCCESS;
    if (memory_read(0x2000) != 0x89 || memory_read(0x2001) != 0x87) {
        result = STATUS_DEVICE_NOT_READY;
    } else if (((memory_read(0x180d) >> 4) & 3) != 1 || memory_read(0x1841) != 255 || (memory_read(0x180a) & 64)) {
        result = STATUS_DEVICE_NOT_READY;
    } else {
        out[0] = memory_read(0x0558);
        out[2] = memory_read(0x1808);
        result = STATUS_DEVICE_NOT_READY;
        for (new i = 0; i < 3; i++) {
            new rpm_hi = memory_read(0x055c);
            new rpm_lo = memory_read(0x055d);
            if (rpm_hi == memory_read(0x055c)) {
                out[1] = (rpm_hi << 8) | rpm_lo;
                result = STATUS_SUCCESS;
                break;
            }
        }
    }
    select_sub(0x11); io_out_byte(0x2f, hi);
    select_sub(0x10); io_out_byte(0x2f, lo);
    reg_write(0x2e, sub);
    io_out_byte(0x2e, index);
    return result;
}
NTSTATUS:wait_status(mask, expected) {
    for (new i = 0; i < 250; i++) {
        if ((io_in_byte(0x6e) & mask) == expected) return STATUS_SUCCESS;
        microsleep(1000);
    }
    return STATUS_TIMEOUT;
}
NTSTATUS:command(command) {
    if (io_in_byte(0x6e) & 3) return STATUS_DEVICE_BUSY;
    io_out_byte(0x6e, command);
    return wait_status(2, 0);
}
NTSTATUS:write_pwm(value) {
    new NTSTATUS:result = command(0x7d);
    if (result != STATUS_SUCCESS) return result;
    io_out_byte(0x6a, value);
    return wait_status(2, 0);
}
/// Validate IT8987, PMC3 ports, PWM6 and capture original PWM.
/// Must hold Global\Access_ISABUS.HTP.Method across each ioctl.
/// No input/output. Usermode must validate A515-54G / Doc_WC / V1.24 first.
DEFINE_IOCTL_SIZED(ioctl_validate, 0, 0) {
    if (g_ready) return STATUS_SUCCESS;
    new index = io_in_byte(0x2e);
    new NTSTATUS:result = STATUS_SUCCESS;
    if (reg_read(0x20) != 0x89 || reg_read(0x21) != 0x87) {
        result = STATUS_NOT_FOUND;
    } else {
        new ldn = reg_read(7);
        reg_write(7, 0x17);
        if (reg_read(0x30) != 1 || reg_read(0x60) != 0 || reg_read(0x61) != 0x6a || reg_read(0x62) != 0 || reg_read(0x63) != 0x6e) result = STATUS_DEVICE_NOT_READY;
        reg_write(7, ldn);
    }
    io_out_byte(0x2e, index);
    if (result != STATUS_SUCCESS) return result;
    new values[3]; result = sample(values);
    if (result != STATUS_SUCCESS) return result;
    result = command(0x7e);
    if (result != STATUS_SUCCESS) return result;
    result = wait_status(3, 1);
    if (result != STATUS_SUCCESS) return result;
    g_original = io_in_byte(0x6a);
    if (g_original < 1 || g_original > 255) return STATUS_DEVICE_NOT_READY;
    g_ready = true;
    return STATUS_SUCCESS;
}
/// Read CPU Celsius, physical fan RPM, PWM6. Output has exactly three cells.
DEFINE_IOCTL_SIZED(ioctl_sample, 0, 3) {
    if (!g_ready) return STATUS_DEVICE_NOT_READY;
    return sample(out);
}
/// Request PWM6 183–255. Reject every value outside the bounded manual range.
/// Thermal validation is repeated here, in addition to the userspace controller.
DEFINE_IOCTL_SIZED(ioctl_set_pwm, 1, 0) {
    if (!g_ready) return STATUS_DEVICE_NOT_READY;
    new pwm = in[0];
    if (pwm < 183 || pwm > 255) return STATUS_INVALID_PARAMETER;
    new values[3]; new NTSTATUS:result = sample(values);
    if (result != STATUS_SUCCESS) return result;
    if (values[0] > 125) return STATUS_DEVICE_NOT_READY;
    if (values[0] >= 85) pwm = 255;
    if (!g_changed) {
        result = command(0x7e);
        if (result != STATUS_SUCCESS) return result;
        result = wait_status(3, 1);
        if (result != STATUS_SUCCESS) return result;
        g_original = io_in_byte(0x6a);
        if (g_original < 1 || g_original > 255) return STATUS_DEVICE_NOT_READY;
    }
    g_changed = true;
    return write_pwm(pwm);
}
/// Restore the captured duty; firmware automatic regulation stays enabled.
DEFINE_IOCTL_SIZED(ioctl_restore, 0, 0) {
    if (!g_ready || !g_changed) return STATUS_SUCCESS;
    new NTSTATUS:result = write_pwm(g_original);
    if (result == STATUS_SUCCESS) g_changed = false;
    return result;
}
public NTSTATUS:unload() {
    if (g_ready && g_changed) return write_pwm(g_original);
    return STATUS_SUCCESS;
}
NTSTATUS:main() { return STATUS_SUCCESS; }

