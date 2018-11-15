# Keyring Fixer
This program reads a "old" mysql 5.7.20 keyring_file and writes a 'fixed'
keyring file compatible with 5.7.23 for percona_binlog key versioning.

The problem is that 5.7.20 names the key "percona_binlog" and 5.7.23 has
since versioned the keys, so it expects at least "percona_binlog:0".

You can't just change the name in the file because other data structures
then break in the keyring file. This program solves this problem by
properly re-writing the entire keyring and all required data elements get
updated.

Dan Smythe <dsmythe@godaddy.com> 11/14/2018
## Setup
There are no dependeny pip modules to install. You can copy this python program to your server, make it executable, and run it. I have run it using python2.6 and python2.7 so it should have fairly wide compatibility.
## Usage
The script takes a few switches:
```
 -i, --input-keyring /path/to/keyring_file
    The path to the keyring you would like to read. Must exist.
    
 -o, --output-keyrung /path/to/new_keyring_file
    The path of the new keyring_file you would like to make. Must not exist and be writable.
    
 -f, --fix-percona-binlog
    If and when the program comes across the "percona_binlog" key, it will rename it "percona_binlog:0"
```
## Example
Example of invoking program and fixing an old percona_binlog key
```
[root@p3dldantest1-a ~]# ./fix_keyring.py -f -i /var/lib/mysql_data/3306/keyring -o test-keyring
Keyring file version: 1.0
Loaded Key: INNODBKey-********-****-****-****-************-1 Type: AES, User: SYSTEM
Loaded Key: percona_binlog Type: AES, User: SYSTEM
Wrote new keyring header
Wrote Key: INNODBKey-********-****-****-****-************-1 Type: AES, User: SYSTEM
Fixing percona_binlog key
Wrote Key: percona_binlog:0 Type: AES, User: SYSTEM

[root@p3dldantest1-a ~]# ls -la /var/lib/mysql_data/3306/keyring test-keyring
-rw-r--r-- 1 dsmythe gdstaff 235 Nov 14 15:02 /var/lib/mysql_data/3306/keyring
-rw-r--r-- 1 root    root    235 Nov 15 08:16 test-keyring

[root@p3dldantest1-a ~]# cat test-keyring
Keyring file version:1.0@@@garbage@@@INNODBKey-********-****-****-****-************-1AES@@@garbage@@@percona_binlog:0AESZU5S@@@garbage@@@EOF
```
Example of invoking the program on a keyring with more keys ( but no fix needed ) this does nothing but copy the file.
```
[root@p3dldantest1-a ~]# ./Key.py f -i /var/lib/mysql_data/3306/keyring -o test-keyring
Keyring file version: 1.0
Loaded Key: ultimate Type: AES, User: root@localhost
Loaded Key: percona_binlog:0 Type: AES, User: SYSTEM
Loaded Key: MyKeytest Type: AES, User: root@localhost
Loaded Key: MyKey Type: DSA, User: root@localhost
Loaded Key: foobar Type: AES, User: root@localhost
Wrote new keyring header
Wrote Key: ultimate Type: AES, User: root@localhost
Wrote Key: percona_binlog:0 Type: AES, User: SYSTEM
Wrote Key: MyKeytest Type: AES, User: root@localhost
Wrote Key: MyKey Type: DSA, User: root@localhost
Wrote Key: foobar Type: AES, User: root@localhost

[root@p3dldantest1-a ~]# ls -la /var/lib/mysql_data/3306/keyring test-keyring
-rw-r--r-- 1 root  root  779 Nov 15 08:21 test-keyring
-rw-r----- 1 mysql mysql 779 Nov 14 17:15 /var/lib/mysql_data/3306/keyring
```

# How it works
Each key has a header structure of 5 bigints:

1. POD Size ( total, complete length of entire thing including this ), 8-bytes
2. Key ID ( name ) length of key id string, 8-bytes
3. Key Type ( AES ) length of key type string, 8-bytes
4. User ID ( username@localhost ) length of user id string, 8-bytes
5. The actual obfuscated key's string length, 8-bytes

After the header ( which is inherently padded to 8-byte boundary... ), The actual data follows:

1. The Key ID ( name ) ascii string
2. The Key Type ( AES ) ascii string
3. The User ID ( username@localhost ) ascii string
4. The key ( obfuscated ) binary string

This is then padded to the nearest 8-byte boundary with null bytes. Once we understand the format of this file, we now know how we can read and re-write it with a different key name. The main thing that happens is that the "Key ID" string gets modified to "percona_binlog:0" which adds 2 characters to the string. When this gets written back to the file, the second header value "Key ID string length" has to be incremented by 2 to indicate that the string is a bit longer. This additional string length also increases the size of the first header item which is the POD size, and lastly these changes could change how much padding is required. So this program makes the necessary adjustments to the header values and padding for mysqld to be able to read the newly named key.

# Things I'd like to add
I have a few other ideas how this program could be useful. 
- [ ] Ability to de-obfuscate the keys themselves, for manual export
- [ ] Ability to manually add or remove keys from the keyring
- [ ] Ability to modify the user who created the key(s)
