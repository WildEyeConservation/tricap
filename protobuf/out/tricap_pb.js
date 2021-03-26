/*eslint-disable block-scoped-var, id-length, no-control-regex, no-magic-numbers, no-prototype-builtins, no-redeclare, no-shadow, no-var, sort-vars*/
"use strict";

var $protobuf = require("protobufjs/minimal");

// Common aliases
var $Reader = $protobuf.Reader, $Writer = $protobuf.Writer, $util = $protobuf.util;

// Exported root namespace
var $root = $protobuf.roots["default"] || ($protobuf.roots["default"] = {});

$root.tricap = (function() {

    /**
     * Namespace tricap.
     * @exports tricap
     * @namespace
     */
    var tricap = {};

    tricap.IpAddress = (function() {

        /**
         * Properties of an IpAddress.
         * @memberof tricap
         * @interface IIpAddress
         * @property {string|null} [ip] IpAddress ip
         */

        /**
         * Constructs a new IpAddress.
         * @memberof tricap
         * @classdesc Represents an IpAddress.
         * @implements IIpAddress
         * @constructor
         * @param {tricap.IIpAddress=} [properties] Properties to set
         */
        function IpAddress(properties) {
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * IpAddress ip.
         * @member {string} ip
         * @memberof tricap.IpAddress
         * @instance
         */
        IpAddress.prototype.ip = "";

        /**
         * Creates a new IpAddress instance using the specified properties.
         * @function create
         * @memberof tricap.IpAddress
         * @static
         * @param {tricap.IIpAddress=} [properties] Properties to set
         * @returns {tricap.IpAddress} IpAddress instance
         */
        IpAddress.create = function create(properties) {
            return new IpAddress(properties);
        };

        /**
         * Encodes the specified IpAddress message. Does not implicitly {@link tricap.IpAddress.verify|verify} messages.
         * @function encode
         * @memberof tricap.IpAddress
         * @static
         * @param {tricap.IIpAddress} message IpAddress message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        IpAddress.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.ip != null && Object.hasOwnProperty.call(message, "ip"))
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.ip);
            return writer;
        };

        /**
         * Encodes the specified IpAddress message, length delimited. Does not implicitly {@link tricap.IpAddress.verify|verify} messages.
         * @function encodeDelimited
         * @memberof tricap.IpAddress
         * @static
         * @param {tricap.IIpAddress} message IpAddress message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        IpAddress.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes an IpAddress message from the specified reader or buffer.
         * @function decode
         * @memberof tricap.IpAddress
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {tricap.IpAddress} IpAddress
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        IpAddress.decode = function decode(reader, length) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.tricap.IpAddress();
            while (reader.pos < end) {
                var tag = reader.uint32();
                switch (tag >>> 3) {
                case 1:
                    message.ip = reader.string();
                    break;
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes an IpAddress message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof tricap.IpAddress
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {tricap.IpAddress} IpAddress
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        IpAddress.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies an IpAddress message.
         * @function verify
         * @memberof tricap.IpAddress
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        IpAddress.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.ip != null && message.hasOwnProperty("ip"))
                if (!$util.isString(message.ip))
                    return "ip: string expected";
            return null;
        };

        /**
         * Creates an IpAddress message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof tricap.IpAddress
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {tricap.IpAddress} IpAddress
         */
        IpAddress.fromObject = function fromObject(object) {
            if (object instanceof $root.tricap.IpAddress)
                return object;
            var message = new $root.tricap.IpAddress();
            if (object.ip != null)
                message.ip = String(object.ip);
            return message;
        };

        /**
         * Creates a plain object from an IpAddress message. Also converts values to other types if specified.
         * @function toObject
         * @memberof tricap.IpAddress
         * @static
         * @param {tricap.IpAddress} message IpAddress
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        IpAddress.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.defaults)
                object.ip = "";
            if (message.ip != null && message.hasOwnProperty("ip"))
                object.ip = message.ip;
            return object;
        };

        /**
         * Converts this IpAddress to JSON.
         * @function toJSON
         * @memberof tricap.IpAddress
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        IpAddress.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        return IpAddress;
    })();

    tricap.WifiSetup = (function() {

        /**
         * Properties of a WifiSetup.
         * @memberof tricap
         * @interface IWifiSetup
         * @property {string|null} [ssid] WifiSetup ssid
         * @property {string|null} [password] WifiSetup password
         */

        /**
         * Constructs a new WifiSetup.
         * @memberof tricap
         * @classdesc Represents a WifiSetup.
         * @implements IWifiSetup
         * @constructor
         * @param {tricap.IWifiSetup=} [properties] Properties to set
         */
        function WifiSetup(properties) {
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * WifiSetup ssid.
         * @member {string} ssid
         * @memberof tricap.WifiSetup
         * @instance
         */
        WifiSetup.prototype.ssid = "";

        /**
         * WifiSetup password.
         * @member {string} password
         * @memberof tricap.WifiSetup
         * @instance
         */
        WifiSetup.prototype.password = "";

        /**
         * Creates a new WifiSetup instance using the specified properties.
         * @function create
         * @memberof tricap.WifiSetup
         * @static
         * @param {tricap.IWifiSetup=} [properties] Properties to set
         * @returns {tricap.WifiSetup} WifiSetup instance
         */
        WifiSetup.create = function create(properties) {
            return new WifiSetup(properties);
        };

        /**
         * Encodes the specified WifiSetup message. Does not implicitly {@link tricap.WifiSetup.verify|verify} messages.
         * @function encode
         * @memberof tricap.WifiSetup
         * @static
         * @param {tricap.IWifiSetup} message WifiSetup message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        WifiSetup.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.ssid != null && Object.hasOwnProperty.call(message, "ssid"))
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.ssid);
            if (message.password != null && Object.hasOwnProperty.call(message, "password"))
                writer.uint32(/* id 2, wireType 2 =*/18).string(message.password);
            return writer;
        };

        /**
         * Encodes the specified WifiSetup message, length delimited. Does not implicitly {@link tricap.WifiSetup.verify|verify} messages.
         * @function encodeDelimited
         * @memberof tricap.WifiSetup
         * @static
         * @param {tricap.IWifiSetup} message WifiSetup message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        WifiSetup.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a WifiSetup message from the specified reader or buffer.
         * @function decode
         * @memberof tricap.WifiSetup
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {tricap.WifiSetup} WifiSetup
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        WifiSetup.decode = function decode(reader, length) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.tricap.WifiSetup();
            while (reader.pos < end) {
                var tag = reader.uint32();
                switch (tag >>> 3) {
                case 1:
                    message.ssid = reader.string();
                    break;
                case 2:
                    message.password = reader.string();
                    break;
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a WifiSetup message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof tricap.WifiSetup
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {tricap.WifiSetup} WifiSetup
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        WifiSetup.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a WifiSetup message.
         * @function verify
         * @memberof tricap.WifiSetup
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        WifiSetup.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.ssid != null && message.hasOwnProperty("ssid"))
                if (!$util.isString(message.ssid))
                    return "ssid: string expected";
            if (message.password != null && message.hasOwnProperty("password"))
                if (!$util.isString(message.password))
                    return "password: string expected";
            return null;
        };

        /**
         * Creates a WifiSetup message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof tricap.WifiSetup
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {tricap.WifiSetup} WifiSetup
         */
        WifiSetup.fromObject = function fromObject(object) {
            if (object instanceof $root.tricap.WifiSetup)
                return object;
            var message = new $root.tricap.WifiSetup();
            if (object.ssid != null)
                message.ssid = String(object.ssid);
            if (object.password != null)
                message.password = String(object.password);
            return message;
        };

        /**
         * Creates a plain object from a WifiSetup message. Also converts values to other types if specified.
         * @function toObject
         * @memberof tricap.WifiSetup
         * @static
         * @param {tricap.WifiSetup} message WifiSetup
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        WifiSetup.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.defaults) {
                object.ssid = "";
                object.password = "";
            }
            if (message.ssid != null && message.hasOwnProperty("ssid"))
                object.ssid = message.ssid;
            if (message.password != null && message.hasOwnProperty("password"))
                object.password = message.password;
            return object;
        };

        /**
         * Converts this WifiSetup to JSON.
         * @function toJSON
         * @memberof tricap.WifiSetup
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        WifiSetup.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        return WifiSetup;
    })();

    tricap.Message = (function() {

        /**
         * Properties of a Message.
         * @memberof tricap
         * @interface IMessage
         * @property {tricap.Message.MessageType|null} [msgType] Message msgType
         * @property {tricap.IIpAddress|null} [ip] Message ip
         * @property {tricap.IWifiSetup|null} [wifi] Message wifi
         */

        /**
         * Constructs a new Message.
         * @memberof tricap
         * @classdesc Represents a Message.
         * @implements IMessage
         * @constructor
         * @param {tricap.IMessage=} [properties] Properties to set
         */
        function Message(properties) {
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * Message msgType.
         * @member {tricap.Message.MessageType} msgType
         * @memberof tricap.Message
         * @instance
         */
        Message.prototype.msgType = 0;

        /**
         * Message ip.
         * @member {tricap.IIpAddress|null|undefined} ip
         * @memberof tricap.Message
         * @instance
         */
        Message.prototype.ip = null;

        /**
         * Message wifi.
         * @member {tricap.IWifiSetup|null|undefined} wifi
         * @memberof tricap.Message
         * @instance
         */
        Message.prototype.wifi = null;

        /**
         * Creates a new Message instance using the specified properties.
         * @function create
         * @memberof tricap.Message
         * @static
         * @param {tricap.IMessage=} [properties] Properties to set
         * @returns {tricap.Message} Message instance
         */
        Message.create = function create(properties) {
            return new Message(properties);
        };

        /**
         * Encodes the specified Message message. Does not implicitly {@link tricap.Message.verify|verify} messages.
         * @function encode
         * @memberof tricap.Message
         * @static
         * @param {tricap.IMessage} message Message message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Message.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.msgType != null && Object.hasOwnProperty.call(message, "msgType"))
                writer.uint32(/* id 1, wireType 0 =*/8).int32(message.msgType);
            if (message.ip != null && Object.hasOwnProperty.call(message, "ip"))
                $root.tricap.IpAddress.encode(message.ip, writer.uint32(/* id 2, wireType 2 =*/18).fork()).ldelim();
            if (message.wifi != null && Object.hasOwnProperty.call(message, "wifi"))
                $root.tricap.WifiSetup.encode(message.wifi, writer.uint32(/* id 3, wireType 2 =*/26).fork()).ldelim();
            return writer;
        };

        /**
         * Encodes the specified Message message, length delimited. Does not implicitly {@link tricap.Message.verify|verify} messages.
         * @function encodeDelimited
         * @memberof tricap.Message
         * @static
         * @param {tricap.IMessage} message Message message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Message.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a Message message from the specified reader or buffer.
         * @function decode
         * @memberof tricap.Message
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {tricap.Message} Message
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Message.decode = function decode(reader, length) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.tricap.Message();
            while (reader.pos < end) {
                var tag = reader.uint32();
                switch (tag >>> 3) {
                case 1:
                    message.msgType = reader.int32();
                    break;
                case 2:
                    message.ip = $root.tricap.IpAddress.decode(reader, reader.uint32());
                    break;
                case 3:
                    message.wifi = $root.tricap.WifiSetup.decode(reader, reader.uint32());
                    break;
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a Message message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof tricap.Message
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {tricap.Message} Message
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Message.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a Message message.
         * @function verify
         * @memberof tricap.Message
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        Message.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.msgType != null && message.hasOwnProperty("msgType"))
                switch (message.msgType) {
                default:
                    return "msgType: enum value expected";
                case 0:
                case 1:
                    break;
                }
            if (message.ip != null && message.hasOwnProperty("ip")) {
                var error = $root.tricap.IpAddress.verify(message.ip);
                if (error)
                    return "ip." + error;
            }
            if (message.wifi != null && message.hasOwnProperty("wifi")) {
                var error = $root.tricap.WifiSetup.verify(message.wifi);
                if (error)
                    return "wifi." + error;
            }
            return null;
        };

        /**
         * Creates a Message message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof tricap.Message
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {tricap.Message} Message
         */
        Message.fromObject = function fromObject(object) {
            if (object instanceof $root.tricap.Message)
                return object;
            var message = new $root.tricap.Message();
            switch (object.msgType) {
            case "IP_ADDRESS":
            case 0:
                message.msgType = 0;
                break;
            case "WIFI_SETUP":
            case 1:
                message.msgType = 1;
                break;
            }
            if (object.ip != null) {
                if (typeof object.ip !== "object")
                    throw TypeError(".tricap.Message.ip: object expected");
                message.ip = $root.tricap.IpAddress.fromObject(object.ip);
            }
            if (object.wifi != null) {
                if (typeof object.wifi !== "object")
                    throw TypeError(".tricap.Message.wifi: object expected");
                message.wifi = $root.tricap.WifiSetup.fromObject(object.wifi);
            }
            return message;
        };

        /**
         * Creates a plain object from a Message message. Also converts values to other types if specified.
         * @function toObject
         * @memberof tricap.Message
         * @static
         * @param {tricap.Message} message Message
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        Message.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.defaults) {
                object.msgType = options.enums === String ? "IP_ADDRESS" : 0;
                object.ip = null;
                object.wifi = null;
            }
            if (message.msgType != null && message.hasOwnProperty("msgType"))
                object.msgType = options.enums === String ? $root.tricap.Message.MessageType[message.msgType] : message.msgType;
            if (message.ip != null && message.hasOwnProperty("ip"))
                object.ip = $root.tricap.IpAddress.toObject(message.ip, options);
            if (message.wifi != null && message.hasOwnProperty("wifi"))
                object.wifi = $root.tricap.WifiSetup.toObject(message.wifi, options);
            return object;
        };

        /**
         * Converts this Message to JSON.
         * @function toJSON
         * @memberof tricap.Message
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        Message.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * MessageType enum.
         * @name tricap.Message.MessageType
         * @enum {number}
         * @property {number} IP_ADDRESS=0 IP_ADDRESS value
         * @property {number} WIFI_SETUP=1 WIFI_SETUP value
         */
        Message.MessageType = (function() {
            var valuesById = {}, values = Object.create(valuesById);
            values[valuesById[0] = "IP_ADDRESS"] = 0;
            values[valuesById[1] = "WIFI_SETUP"] = 1;
            return values;
        })();

        return Message;
    })();

    return tricap;
})();

module.exports = $root;
