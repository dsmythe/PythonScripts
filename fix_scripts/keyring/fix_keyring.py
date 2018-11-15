#!/usr/bin/python
"""
    This program reads a "old" mysql 5.7.20 keyring_file and writes a 'fixed'
    keyring file compatible with 5.7.23 for percona_binlog key versioning.

    The problem is that 5.7.20 names the key "percona_binlog" and 5.7.23 has
    since versioned the keys, so it expects at least "percona_binlog:0".

    You can't just change the name in the file because other data structures
    then break in the keyring file. This program solves this problem by
    properly re-writing the entire keyring and all required data elements get
    updated.

    Dan Smythe <dsmythe@godaddy.com> 11/14/2018
"""
import os
from optparse import OptionParser
import struct

class Key(object):
    """
        Class representing a key in the keyring file. Each key in the keyring
        has the following attributes:

        key_id   = The friendly name of the key
        key_type = The key type, such as RSA, AES
        user_id  = The mysql user whom created the key, if the key is a system
            key, it has no data in this field.
        key      = The obfuscated key bits.

        TODO: Implement de-obfuscation and re-obfuscation to support exporting
            or importing keys manually, outside of mysqld.
    """
    pod_size = None
    key_id   = None
    key_type = None
    user_id  = None
    key      = None

    def __init__(self, key_id, key_type, user_id, key):
        """
            Unlikely to do this yourself, see the read() classmethod.
        """
        self.key_id   = key_id
        self.key_type = key_type
        self.user_id  = user_id
        self.key      = key

    def pod_size(self):
        """
            Returns the "POD Size" - This is the total length of this key element
                Including the int for the pod size itself.

            4 * struct.calcsize('Q') = 4 unsigned bigints which sequentially define
            the lengths of the following 4 strings

            Plus the actual length of the 4 strings

            Plus another bigint for the pod size value itself
        """
        return 4 * struct.calcsize('Q') + len(self.key_id) + len(self.key_type) + len(self.user_id) + len(self.key) + struct.calcsize('Q')

    def write(self, outfile):
        """
            Writes this key to the outfile file-like object.

            Each key has a header structure of 5 bigints:
                1st - POD Size ( total, complete length of entire thing including this ), 8-bytes
                2nd - Key ID ( name ) string length, 8-bytes
                3rd - Key Type ( AES ) string length, 8-bytes
                4th - User ID ( username@localhost ) string length, 8-bytes
                5th - The actual obfuscated key's string length, 8-bytes

            After the header ( which is inherently padded to 8-byte boundary... ),

            The actual data follows:
                1st - The Key ID ( name ) ascii string
                2nd - The Key Type ( AES ) ascii string
                3rd - The User ID ( username@localhost ) ascii string
                4th - The key ( obfuscated ) binary string

            Finally the entire thing is padded to the nearest 8-byte boundary.
        """
        # Write 'header'
        outfile.write(struct.pack('QQQQQ', self.pod_size(), len(self.key_id), len(self.key_type), len(self.user_id), len(self.key)))
        # Write values
        outfile.write(self.key_id)
        outfile.write(self.key_type)
        outfile.write(self.user_id)
        outfile.write(self.key)
        # Write padding null bytes if needed.
        self.write_padding(outfile)

    @classmethod
    def read(cls, infile):
        """
            Reads a key from the current position in the infile. Returns an instance of Key()

            See the comment for write() for a description of the data structure.

            The infile must be positioned at the beginning of a key, which would
            be the 8-byte "POD Size" header value. If implementing this yourself,
            that means you'll at the least have to seek() the infile past the version
            string at the front of the keyring_file. Keyring file begins as:
            "Keyring file version:1.0BBBBBBBB" Where BBBBBBBB is the 8 byte POD Size
            Cheaters can just seek(24) to get to the right spot.

            After reading the key, this method will leave the file pointed at the
            beginning of the next key, since this method also consumes the null byte
            padding between them.

            If at the EOF though, the file will be pointed so that infile.read(1) will
            be the 'E' in EOF. Yes, there is actually a literal ascii EOF at the end
            of the file.

            We catch the exception if the unpack fails, to notify the read loop that
            we have reached EOF. Tsk tsk.
        """
        try:
            # Read the header bytes of all the thing-lengths
            key_pod_size, key_id_len, key_type_len, user_id_len, key_len = struct.unpack('QQQQQ', infile.read(struct.calcsize('QQQQQ')))
        except struct.error as e:
            # Catch this exception so we know when EOF is reached.
            return False
        # Read the data according to the lengths we read.
        key_id = infile.read(key_id_len)
        key_type = infile.read(key_type_len)
        user_id = infile.read(user_id_len)
        key = infile.read(key_len)
        # Read ( and discard ) any trailing padding. We'll need to recalculate it anyway
        cls.read_padding(infile)
        # Return an instance of Key()
        return cls(key_id, key_type, user_id, key)

    @staticmethod
    def read_padding(infile):
        """
            Reads the calculated amount of padding there should now be in the infile.
        """
        padding = (8 - (infile.tell()%8)) % 8
        return infile.read(padding)

    @staticmethod
    def write_padding(outfile):
        """
            Writes null bytes to the nearest 8-byte boundary in outfile.
        """
        padding = (8 - (outfile.tell()%8)) % 8
        return outfile.write(struct.pack('{0}x'.format(padding)))


def read_keyring_header(infile):
    """
        Reads the Keyring version text from the beginning of the infile.
        Returns the keyring version text.
    """
    # Get to the : between "Keyring file version:" and the version string "1.0"
    buf = ''
    header = ''
    while buf != ':':
        buf = infile.read(1)
        header += buf

    version_string = infile.read(3)
    header += version_string
    print("Keyring file version: {0}".format(version_string))
    return header


def main(options):
    """
        Main execution.

        1 - Open our source file and destination files
        2 - Read out the version header of the source file
        3 - Load all the Keys contained in the source file
        4 - Write version header to outfile
        5 - Write each key to the outfile, fixing the percona_binlog key name if -f was provided
        6 - Write the "EOF" at the end of the file.

        TODO: Support key de-obfuscation for raw/actual key retrieval
        TODO: Support manually adding/removing keys
        TODO: Support modifying key users
        TODO: Support in-place modification of source file
    """

    if not os.path.isfile(options.infile):
        raise RuntimeError("Input file {0} does not exist?".format(options.infile))

    if os.path.isfile(options.outfile):
        raise RuntimeError("Output file {0} already exists.".format(options.outfile))

    rh = open(options.infile, 'rb')
    wh = open(options.outfile, 'wb')

    # Loading phase
    header = read_keyring_header(rh)

    keys = []

    while True:
        key = Key.read(rh)
        if key is False:
            break
        print('Loaded Key: {0} Type: {1}, User: {2}'.format(key.key_id, key.key_type, 'SYSTEM' if key.user_id is '' else key.user_id))
        keys.append(key)

    # Writing phase
    wh.write(header)
    print("Wrote new keyring header")

    for key in keys:
        if key.key_id == 'percona_binlog' and options.fix is True:
            print("Fixing percona_binlog key")
            key.key_id = 'percona_binlog:0'
        elif key.key_id == 'percona_binlog':
            print("You have a un-versioned percona_binlog key, consider using -f to fix it.")
        key.write(wh)
        print('Wrote Key: {0} Type: {1}, User: {2}'.format(key.key_id, key.key_type, 'SYSTEM' if key.user_id is '' else key.user_id))

    wh.write('EOF')


if __name__ == '__main__':
    # Usage is what gets printed out in some help formats.
    usage = "Usage: %prog -i INPUT_KEYRING -o OUTPUT_KEYRING"

    # This creates the option parses and sets the usage string.
    parser = OptionParser(usage=usage)

    parser.add_option("-i", "--input-keyring",
            dest="infile", default=False,
            help='The keyring file to read.')

    parser.add_option("-o", "--output-keyring",
            dest="outfile", default=False,
            help='The new keyring file to create.')

    parser.add_option("-f", "--fix-percona-binlog", action='store_true',
            dest="fix", default=False,
            help='Update percona_binlog key to be versioned eg, percona_binlog:0')

    # Parse our invoked arguments.
    (options,args) = parser.parse_args()

    main(options)

