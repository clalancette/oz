import Guest

def generate_iso(output_iso, input_dir):
    Guest.subprocess_check_output(["mkisofs", "-r", "-T", "-J", "-V",
                                   "Custom", "-b", "isolinux/isolinux.bin",
                                   "-c", "isolinux/boot.cat",
                                   "-no-emul-boot", "-boot-load-size", "4",
                                   "-boot-info-table", "-v", "-v",
                                   "-o", output_iso, input_dir ])
