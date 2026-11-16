import re
import time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import serial
import serial.tools.list_ports


APP_NAME = 'SS Serial Generator'
APP_VERSION = '1.0.0'


def format_scc_line(address, cable, units, calibration):
    if address not in ('A', 'B', 'C', 'D'):
        raise ValueError('Address must be A, B, C, or D.')
    if units not in ('M', 'F'):
        raise ValueError('Units must be M or F.')
    if not re.fullmatch(r'[+-]\d{4}', calibration):
        raise ValueError('Calibration must contain a sign and four digits.')
    if not 0 <= cable <= 99999.9:
        raise ValueError('Cable value must be between 0 and 99999.9.')
    return f'$CC{address}{cable:07.1f}{units}{calibration}\r\n'


class SSSerialGenerator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.serial_port = None
        self.after_id = None
        self.last_sent_at = None

        self.title(f'{APP_NAME} {APP_VERSION}')
        self.geometry('680x600')
        self.minsize(620, 560)
        self.protocol('WM_DELETE_WINDOW', self.close_window)

        self.build_ui()
        self.refresh_ports()

    def build_ui(self):
        style = ttk.Style(self)
        if 'vista' in style.theme_names():
            style.theme_use('vista')

        main = ttk.Frame(self, padding=14)
        main.grid(row=0, column=0, sticky='nsew')
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, columnspan=3, sticky='ew', pady=(0, 12))
        header.columnconfigure(1, weight=1)

        logo_path = Path(__file__).resolve().with_name('CSA_LOGO.png')
        self.logo_image = tk.PhotoImage(file=str(logo_path)).subsample(8, 8)
        ttk.Label(header, image=self.logo_image).grid(
            row=0, column=0, padx=(0, 14)
        )
        ttk.Label(
            header,
            text=f'{APP_NAME} - SCC serial test tool',
            font=('Segoe UI', 14, 'bold')
        ).grid(row=0, column=1, sticky='w')

        ttk.Label(main, text='Generator COM port:').grid(
            row=1, column=0, sticky='w', padx=(0, 10), pady=4
        )
        self.port = ttk.Combobox(main, state='normal', width=18)
        self.port.grid(row=1, column=1, sticky='ew', pady=4)
        self.refresh_button = ttk.Button(
            main, text='Refresh Ports', command=self.refresh_ports
        )
        self.refresh_button.grid(row=1, column=2, padx=(8, 0), pady=4)

        settings = ttk.LabelFrame(main, text='SCC Data Settings', padding=10)
        settings.grid(row=2, column=0, columnspan=3, sticky='ew', pady=(8, 10))
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)

        self.address = tk.StringVar(value='A')
        self.units = tk.StringVar(value='M')
        self.calibration = tk.StringVar(value='+0357')
        self.cable = tk.DoubleVar(value=0.7)
        self.direction = tk.StringVar(value='PAYING OUT')
        self.speed = tk.DoubleVar(value=0.5)
        self.interval = tk.IntVar(value=500)

        ttk.Label(settings, text='Address:').grid(
            row=0, column=0, sticky='w', padx=(0, 8), pady=4
        )
        ttk.Combobox(
            settings, textvariable=self.address, values=('A', 'B', 'C', 'D'),
            state='readonly', width=8
        ).grid(row=0, column=1, sticky='w', pady=4)

        ttk.Label(settings, text='Units:').grid(
            row=0, column=2, sticky='w', padx=(16, 8), pady=4
        )
        ttk.Combobox(
            settings, textvariable=self.units, values=('M', 'F'),
            state='readonly', width=8
        ).grid(row=0, column=3, sticky='w', pady=4)

        ttk.Label(settings, text='Calibration:').grid(
            row=1, column=0, sticky='w', padx=(0, 8), pady=4
        )
        ttk.Entry(settings, textvariable=self.calibration, width=12).grid(
            row=1, column=1, sticky='w', pady=4
        )

        ttk.Label(settings, text='Starting cable value:').grid(
            row=1, column=2, sticky='w', padx=(16, 8), pady=4
        )
        ttk.Spinbox(
            settings, textvariable=self.cable, from_=0, to=99999.9,
            increment=0.1, format='%.1f', width=12
        ).grid(row=1, column=3, sticky='w', pady=4)

        ttk.Label(settings, text='Direction:').grid(
            row=2, column=0, sticky='w', padx=(0, 8), pady=4
        )
        ttk.Combobox(
            settings, textvariable=self.direction,
            values=('PAYING OUT', 'HAULING IN', 'STOPPED'),
            state='readonly', width=16
        ).grid(row=2, column=1, sticky='w', pady=4)

        ttk.Label(settings, text='Speed (units/second):').grid(
            row=2, column=2, sticky='w', padx=(16, 8), pady=4
        )
        ttk.Spinbox(
            settings, textvariable=self.speed, from_=0, to=1000,
            increment=0.1, format='%.2f', width=12
        ).grid(row=2, column=3, sticky='w', pady=4)

        ttk.Label(settings, text='Send interval:').grid(
            row=3, column=0, sticky='w', padx=(0, 8), pady=4
        )
        ttk.Spinbox(
            settings, textvariable=self.interval, from_=100, to=5000,
            increment=100, format='%d', width=8
        ).grid(row=3, column=1, sticky='w', pady=4)
        ttk.Label(settings, text='ms').grid(
            row=3, column=2, sticky='w', padx=(6, 0), pady=4
        )

        instructions = ttk.Label(
            main,
            text=(
                'Connect the generator and CCN to opposite ends of a virtual '
                'COM pair or physical RS-232 null-modem link. The generator '
                'sends at 9600 baud, 8-N-1.'
            ),
            wraplength=630
        )
        instructions.grid(row=3, column=0, columnspan=3, sticky='w', pady=(0, 8))

        buttons = ttk.Frame(main)
        buttons.grid(row=4, column=0, columnspan=3, sticky='ew', pady=(0, 8))
        self.start_button = ttk.Button(
            buttons, text='Start Sending', command=self.start_generator
        )
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(
            buttons, text='Stop', command=self.stop_generator, state='disabled'
        )
        self.stop_button.pack(side='left', padx=(8, 0))

        self.status = tk.StringVar(value='Status: Stopped')
        ttk.Label(main, textvariable=self.status).grid(
            row=5, column=0, columnspan=3, sticky='nw', pady=(0, 4)
        )
        self.preview = tk.StringVar(value='Last SCC line: ---')
        ttk.Label(main, textvariable=self.preview, font=('Consolas', 10)).grid(
            row=6, column=0, columnspan=3, sticky='w', pady=(0, 6)
        )

        output_frame = ttk.Frame(main)
        output_frame.grid(row=7, column=0, columnspan=3, sticky='nsew')
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)
        self.output = tk.Text(output_frame, height=8, wrap='none', state='disabled')
        self.output.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(
            output_frame, orient='vertical', command=self.output.yview
        )
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.output.configure(yscrollcommand=scrollbar.set)
        main.rowconfigure(7, weight=1)

        footer = ttk.Label(
            main,
            text='Test utility only - does not control an SCC counter.'
        )
        footer.grid(row=8, column=0, columnspan=3, sticky='w', pady=(8, 0))

    def refresh_ports(self):
        selected = self.port.get()
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port.configure(values=ports)
        if selected:
            self.port.set(selected)
        elif ports:
            self.port.set(ports[0])

    def start_generator(self):
        port_name = self.port.get().strip()
        if not port_name:
            messagebox.showwarning('No COM Port', 'Select a COM port first.')
            return

        try:
            format_scc_line(
                self.address.get(),
                self.cable.get(),
                self.units.get(),
                self.calibration.get().strip()
            )
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning('Invalid SCC Settings', str(exc))
            return

        try:
            self.serial_port = serial.Serial(
                port=port_name,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0,
                write_timeout=1
            )
        except (serial.SerialException, OSError, ValueError) as exc:
            messagebox.showerror(
                'COM Port Error', f'Could not open {port_name}: {exc}'
            )
            self.serial_port = None
            return

        self.last_sent_at = time.monotonic()
        self.status.set(f'Status: Sending on {port_name}')
        self.start_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.send_next_line()

    def send_next_line(self):
        self.after_id = None
        if self.serial_port is None:
            return

        now = time.monotonic()
        elapsed = 0 if self.last_sent_at is None else now - self.last_sent_at
        change = self.speed.get() * elapsed
        if self.direction.get() == 'PAYING OUT':
            self.cable.set(min(99999.9, self.cable.get() + change))
        elif self.direction.get() == 'HAULING IN':
            self.cable.set(max(0, self.cable.get() - change))
        self.last_sent_at = now

        try:
            line = format_scc_line(
                self.address.get(),
                self.cable.get(),
                self.units.get(),
                self.calibration.get().strip()
            )
            self.serial_port.write(line.encode('ascii'))
        except (serial.SerialException, OSError, ValueError, tk.TclError) as exc:
            self.stop_generator()
            messagebox.showerror('Serial Send Error', str(exc))
            return

        record = line.rstrip('\r\n')
        self.preview.set(f'Last SCC line: {record}')
        self.output.configure(state='normal')
        self.output.insert('end', record + '\n')
        line_count = int(self.output.index('end-1c').split('.')[0])
        if line_count > 20:
            self.output.delete('1.0', '2.0')
        self.output.see('end')
        self.output.configure(state='disabled')

        self.after_id = self.after(self.interval.get(), self.send_next_line)

    def stop_generator(self):
        if self.after_id is not None:
            try:
                self.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None

        if self.serial_port is not None:
            try:
                self.serial_port.close()
            except (serial.SerialException, OSError) as exc:
                messagebox.showwarning('COM Port Close Error', str(exc))
            finally:
                self.serial_port = None

        self.last_sent_at = None
        self.status.set('Status: Stopped')
        self.start_button.configure(state='normal')
        self.stop_button.configure(state='disabled')

    def close_window(self):
        self.stop_generator()
        self.destroy()


def main():
    SSSerialGenerator().mainloop()


if __name__ == '__main__':
    main()
