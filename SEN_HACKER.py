#!/data/data/com.termux/files/usr/bin/python
import os
import sys
import zstandard as zstd
from concurrent.futures import ThreadPoolExecutor
import time
import shutil
import subprocess
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from pyfiglet import Figlet
import traceback
import glob

# ==============================================
# CONFIGURATION
# ==============================================
MAGIC_NUMBER = b'\x28\xB5\x2F\xFD'
DICT_START_HEX = bytes.fromhex("37 A4 30 EC")
MAX_COMPRESSION_LEVEL = 22
MAX_WORKERS = 4  # Parallel threads for decompression
SUPPORTED_DICT_EXTENSIONS = ('.bin', '.dict', '.zstdict', '.zdict')

# ==============================================
# PATH CONFIGURATION (Termux compatible)
# ==============================================
BASE_DIR = "/storage/emulated/0/Download/zsdic/"
INPUT_DIR = os.path.join(BASE_DIR, "INPUT")
REPACK_DIR = os.path.join(BASE_DIR, "REPACK")
DICT_DIR = os.path.join(BASE_DIR, "Dictionary")
UNPACK_DIR = os.path.join(BASE_DIR, "UNPACK")
BACKUP_DIR = os.path.join(BASE_DIR, "Backup_Files")
LOG_DIR = os.path.join(BASE_DIR, "Logs")

# Auto-detected files
ORIGINAL_PAK = None
DICT_FILE = None

# ==============================================
# INITIALIZATION
# ==============================================
console = Console()

def initialize_environment():
    """Create all required directories and install packages"""
    try:
        # Create directories
        os.makedirs(BASE_DIR, exist_ok=True)
        os.makedirs(INPUT_DIR, exist_ok=True)
        os.makedirs(REPACK_DIR, exist_ok=True)
        os.makedirs(DICT_DIR, exist_ok=True)
        os.makedirs(UNPACK_DIR, exist_ok=True)
        os.makedirs(BACKUP_DIR, exist_ok=True)
        os.makedirs(LOG_DIR, exist_ok=True)

        # Install required packages
        console.print("[cyan]Checking for required packages...[/cyan]")
        packages = ['zstandard', 'rich', 'pyfiglet']
        for package in packages:
            try:
                __import__(package)
            except ImportError:
                console.print(f"[yellow]Installing {package}...[/yellow]")
                subprocess.run([sys.executable, "-m", "pip", "install", package], check=True)
        
        return True
    except Exception as e:
        console.print(f"[red]Initialization failed: {str(e)}[/red]")
        traceback.print_exc()
        return False

def detect_files():
    """Auto-detect required files in the input directory"""
    global ORIGINAL_PAK, DICT_FILE
    
    # Detect PAK file
    pak_files = glob.glob(os.path.join(INPUT_DIR, "*.pak"))
    if pak_files:
        ORIGINAL_PAK = pak_files[0]  # Use first found .pak file
        console.print(f"[green]Detected PAK file: {ORIGINAL_PAK}[/green]")
    
    # Auto-select dictionary file
    dict_files = []
    for ext in SUPPORTED_DICT_EXTENSIONS:
        dict_files.extend(glob.glob(os.path.join(DICT_DIR, f"*{ext}")))
    
    if dict_files:
        # Prioritize files with 'dict' in name, then largest file
        dict_files.sort(key=lambda x: (
            -1 if 'dict' in os.path.basename(x).lower() else 0,
            -os.path.getsize(x)
        ))
        DICT_FILE = dict_files[0]
        console.print(f"[green]Selected dictionary: {DICT_FILE}[/green]")
    
    return ORIGINAL_PAK is not None and DICT_FILE is not None

def load_dictionary():
    """Load the Zstandard dictionary file"""
    if not DICT_FILE:
        raise FileNotFoundError("No dictionary file detected")
    
    try:
        with open(DICT_FILE, 'rb') as f:
            return f.read()
    except Exception as e:
        raise RuntimeError(f"Failed to load dictionary: {str(e)}")

def show_banner():
    fig = Figlet(font='bubble')
    banner_text = fig.renderText("SEN_HACKER")
    text = Text.from_ansi(banner_text)
    text.stylize("bold magenta")
    console.clear()
    console.print(text, justify="center")
    console.print("[bold yellow]Advanced ZSDIC PAK Extractor & Repacker[/bold yellow]", justify="center")
    console.print(f"[dim]Version 1.0 | Termux Environment[/dim]\n")

def extract_dictionary_from_pak(pak_file, start_hex):
    """Extract the Zstandard dictionary from the PAK file"""
    with open(pak_file, 'rb') as f:
        data = f.read()
    dict_start = data.find(start_hex)
    if dict_start == -1:
        raise ValueError("Dictionary not found in the PAK file.")
    return data[dict_start:]

def split_segments(data, magic_number):
    """Split the PAK file into individual compressed segments"""
    split_indices = []
    start = 0
    while (start := data.find(magic_number, start)) != -1:
        split_indices.append(start)
        start += len(magic_number)
    split_indices.append(len(data))  # Add EOF

    segments = []
    for i in range(len(split_indices) - 1):
        segment_start = split_indices[i]
        segment_end = split_indices[i + 1]
        segments.append((i + 1, data[segment_start:segment_end]))
    return segments

def decompress_segment(segment, dictionary, output_dir):
    """Decompress a single segment using the provided dictionary"""
    index, segment_data = segment
    try:
        dctx = zstd.ZstdDecompressor(dict_data=dictionary)
        decompressed_data = dctx.decompress(segment_data)

        output_file = os.path.join(output_dir, f'{index:08d}.dat')
        with open(output_file, 'wb') as out_file:
            out_file.write(decompressed_data)

        return f"Decompressed: {index:08d}.dat"
    except Exception as e:
        return f"Error decompressing {index:08d}.dat: {e}"

def extract_segment(pak_file, segment_index, magic_number):
    """Extract a specific segment from the PAK file"""
    with open(pak_file, 'rb') as f:
        data = f.read()
    split_indices = []
    start = 0
    while (start := data.find(magic_number, start)) != -1:
        split_indices.append(start)
        start += len(magic_number)
    split_indices.append(len(data))

    if segment_index < 1 or segment_index > len(split_indices) - 1:
        raise IndexError("Segment index out of range.")

    segment_start = split_indices[segment_index - 1]
    segment_end = split_indices[segment_index]
    return segment_start, segment_end, data[segment_start:segment_end]

def compress_file(input_file, dict_data, compression_level):
    """Compress a file using the provided dictionary"""
    dictionary = zstd.ZstdCompressionDict(dict_data)
    cctx = zstd.ZstdCompressor(dict_data=dictionary, level=compression_level)

    with open(input_file, 'rb') as f:
        input_data = f.read()

    return cctx.compress(input_data)

def replace_segment(pak_file, segment_start, segment_end, compressed_data):
    """Replace a segment in the PAK file with new compressed data"""
    original_segment_size = segment_end - segment_start

    if len(compressed_data) > original_segment_size:
        raise ValueError(f"Compressed data ({len(compressed_data)} bytes) exceeds original size ({original_segment_size} bytes).")

    with open(pak_file, 'rb+') as f:
        f.seek(segment_start)
        f.write(compressed_data)
        if len(compressed_data) < original_segment_size:
            f.write(b'\x00' * (original_segment_size - len(compressed_data)))

def unpack_zsdic():
    """Extract all files from the ZSDIC PAK archive"""
    if not ORIGINAL_PAK:
        console.print("[red]No PAK file detected in input directory![/red]")
        console.print(f"Please place your .pak file in: [cyan]{INPUT_DIR}[/cyan]")
        time.sleep(2)
        main()
        return

    try:
        os.makedirs(UNPACK_DIR, exist_ok=True)
        os.makedirs(BACKUP_DIR, exist_ok=True)
        
        # Create backup
        backup_file = os.path.join(BACKUP_DIR, os.path.basename(ORIGINAL_PAK))
        shutil.copy2(ORIGINAL_PAK, backup_file)
        console.print(f"[green]Backup created: {backup_file}[/green]")

        with open(ORIGINAL_PAK, 'rb') as f:
            data = f.read()

        # Try external dictionary first, fall back to embedded
        try:
            dict_data = load_dictionary()
            console.print("[cyan]Using external dictionary file[/cyan]")
        except Exception as e:
            console.print("[yellow]Using embedded dictionary[/yellow]")
            dict_data = extract_dictionary_from_pak(ORIGINAL_PAK, DICT_START_HEX)

        dictionary = zstd.ZstdCompressionDict(dict_data)

        segments = split_segments(data, MAGIC_NUMBER)
        console.print(f"[cyan]Found {len(segments)} compressed segments[/cyan]")
        console.print(f"[yellow]Decompressing to: {UNPACK_DIR}[/yellow]\n")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for seg in segments:
                futures.append(executor.submit(decompress_segment, seg, dictionary, UNPACK_DIR))
            
            for future in futures:
                result = future.result()
                console.print(f"[green]{result}[/green]")

        console.print(Panel("[bold green]Unpack completed successfully![/bold green]"))
        console.print(f"Extracted files: [cyan]{UNPACK_DIR}[/cyan]")
    except Exception as e:
        console.print(Panel(f"[bold red]Unpack failed: {str(e)}[/bold red]"))
        traceback.print_exc()
    finally:
        time.sleep(2)
        main()

def repack_zsdic():
    """Repack modified files back into a ZSDIC PAK archive"""
    if not ORIGINAL_PAK:
        console.print("[red]No original PAK file detected![/red]")
        time.sleep(1)
        main()
        return

    if not os.path.exists(UNPACK_DIR) or not os.listdir(UNPACK_DIR):
        console.print("[red]No modified files found to repack![/red]")
        console.print(f"Please place your modified .dat files in: [cyan]{UNPACK_DIR}[/cyan]")
        time.sleep(2)
        main()
        return

    try:
        os.makedirs(REPACK_DIR, exist_ok=True)
        repacked_pak = os.path.join(REPACK_DIR, os.path.basename(ORIGINAL_PAK))
        shutil.copy(ORIGINAL_PAK, repacked_pak)
        
        # Load dictionary (external or embedded)
        try:
            dict_data = load_dictionary()
            console.print("[cyan]Using external dictionary file[/cyan]")
        except Exception as e:
            console.print("[yellow]Using embedded dictionary[/yellow]")
            dict_data = extract_dictionary_from_pak(ORIGINAL_PAK, DICT_START_HEX)

        files = sorted([f for f in os.listdir(UNPACK_DIR) if f.endswith('.dat')], 
                      key=lambda x: int(x.split('.')[0]))
        total_files = len(files)

        console.print(f"[cyan]Repacking {total_files} modified files[/cyan]")
        console.print(f"[yellow]Output file: {repacked_pak}[/yellow]\n")

        success_count = 0
        for file_name in files:
            try:
                sequence_number = int(file_name.split('.')[0])
                input_file = os.path.join(UNPACK_DIR, file_name)

                segment_start, segment_end, _ = extract_segment(repacked_pak, sequence_number, MAGIC_NUMBER)

                for compression_level in range(1, MAX_COMPRESSION_LEVEL + 1):
                    try:
                        compressed_data = compress_file(input_file, dict_data, compression_level)
                        replace_segment(repacked_pak, segment_start, segment_end, compressed_data)
                        console.print(f"[green]Reimported: {file_name} (level {compression_level})[/green]")
                        success_count += 1
                        break
                    except ValueError:
                        continue
                else:
                    console.print(f"[red]Failed to reimport: {file_name}[/red]")
            except Exception as e:
                console.print(f"[red]Error processing {file_name}: {e}[/red]")

        console.print(Panel(
            f"[bold green]Repack completed![/bold green]\n"
            f"Successfully processed: [green]{success_count}/{total_files}[/green] files\n"
            f"Output file: [cyan]{repacked_pak}[/cyan]"
        ))
    except Exception as e:
        console.print(Panel(f"[bold red]Repack failed: {str(e)}[/bold red]"))
        traceback.print_exc()
    finally:
        time.sleep(2)
        main()

def main():
    """Main program menu"""
    show_banner()
    
    # Check environment and files
    if not initialize_environment():
        console.print("[red]Failed to initialize environment. Exiting.[/red]")
        time.sleep(2)
        sys.exit(1)
    
    if not detect_files():
        console.print("[yellow]Required files not detected[/yellow]")
        console.print(f"Please ensure you have:\n"
                     f"1. PAK file in [cyan]{INPUT_DIR}[/cyan]\n"
                     f"2. Dictionary file ({', '.join(SUPPORTED_DICT_EXTENSIONS)}) in [cyan]{DICT_DIR}[/cyan]")
        time.sleep(3)

    menu_text = Panel(
        Text(
            "\n1. Unpack ZSDIC PAK\n"
            "2. Repack ZSDIC PAK\n"
            "3. Show File Locations\n"
            "0. Exit\n",
            justify="center",
            style="bold cyan"
        ),
        title="[bold yellow]Main Menu[/bold yellow]",
        border_style="bright_blue"
    )
    console.print(menu_text)
    
    choice = Prompt.ask("Select an option", choices=["0", "1", "2", "3"], default="0")

    if choice == '1':
        unpack_zsdic()
    elif choice == '2':
        repack_zsdic()
    elif choice == '3':
        console.print(Panel(
            f"Input Directory: [cyan]{INPUT_DIR}[/cyan]\n"
            f"Unpack Directory: [cyan]{UNPACK_DIR}[/cyan]\n"
            f"Repack Directory: [cyan]{REPACK_DIR}[/cyan]\n"
            f"Dictionary Directory: [cyan]{DICT_DIR}[/cyan]\n"
            f"Backup Directory: [cyan]{BACKUP_DIR}[/cyan]\n"
            f"Detected PAK File: [cyan]{ORIGINAL_PAK or 'None'}[/cyan]\n"
            f"Detected Dictionary: [cyan]{DICT_FILE or 'None'}[/cyan]",
            title="[bold]File Locations[/bold]"
        ))
        time.sleep(3)
        main()
    elif choice == '0':
        console.print("[bold red]Exiting...[/bold red]")
        time.sleep(0.7)
        sys.exit(0)
    else:
        console.print("[red]Invalid option![/red]")
        time.sleep(0.5)
        main()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[red]Operation cancelled by user[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Critical error: {str(e)}[/red]")
        traceback.print_exc()
        sys.exit(1)